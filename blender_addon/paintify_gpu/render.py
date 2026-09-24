"""Final renders painted by the same pipeline as the viewport overlay.

Each frame is rendered with the scene's engine, saved through the scene's
colour management (so it matches what the viewport overlay samples), painted
at full render size and written to the scene's output. Movie formats are
assembled with Blender's own encoder from a temporary image sequence.
"""

import os
import shutil
import tempfile

import bpy
import numpy as np

from .looks import hold_frames, stroke_scale
from .painter import Painter, texture_from_pixels
from .settings import look_from_settings
from .viewport import render_size

RESULT_IMAGE = "Paintify Render"


class _PngOutput:
    """Temporarily switches image output to 8-bit RGBA PNG, so the render
    result can be saved as the display-referred image the overlay paints."""

    FIELDS = ("media_type", "file_format", "color_mode", "color_depth", "compression")

    def __init__(self, image_settings):
        self.settings = image_settings
        self.saved = {}

    def __enter__(self):
        s = self.settings
        self.saved = {f: getattr(s, f) for f in self.FIELDS if hasattr(s, f)}
        if hasattr(s, "media_type"):
            s.media_type = "IMAGE"
        s.file_format = "PNG"
        s.color_mode = "RGBA"
        s.color_depth = "8"
        s.compression = 15
        return self

    def __exit__(self, *exc):
        for field, value in self.saved.items():
            try:
                setattr(self.settings, field, value)
            except (AttributeError, TypeError, ValueError):
                pass
        return False


def _copy_settings(src, dst):
    """Copies every writable plain property. media_type and file_format go
    first because they decide which of the other values are valid."""
    names = [n for n in ("media_type", "file_format") if hasattr(src, n)]
    for prop in src.bl_rna.properties:
        if (prop.identifier not in names and prop.identifier != "rna_type" and
                not prop.is_readonly and prop.type not in {"POINTER", "COLLECTION"}):
            names.append(prop.identifier)
    for name in names:
        try:
            setattr(dst, name, getattr(src, name))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass


def _output_scene(scene, width, height):
    """A scratch scene that writes painted pixels with the user's output
    settings but no further view transform: they are display-referred
    already, and Standard over sRGB leaves them unchanged."""
    out = bpy.data.scenes.new("Paintify Output")
    r, s = out.render, scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
    r.pixel_aspect_x, r.pixel_aspect_y = s.pixel_aspect_x, s.pixel_aspect_y
    r.fps, r.fps_base = s.fps, s.fps_base
    r.filepath = s.filepath
    r.use_file_extension = s.use_file_extension
    r.dither_intensity = 0.0
    r.use_compositing = False
    r.use_sequencer = True
    _copy_settings(s.image_settings, r.image_settings)
    _copy_settings(s.ffmpeg, r.ffmpeg)
    if hasattr(r.image_settings, "color_management"):
        r.image_settings.color_management = "FOLLOW_SCENE"
    for owner, name, value in ((out.display_settings, "display_device", "sRGB"),
                               (out.view_settings, "view_transform", "Standard"),
                               (out.view_settings, "look", "None"),
                               (out.view_settings, "exposure", 0.0),
                               (out.view_settings, "gamma", 1.0),
                               (out.view_settings, "use_curve_mapping", False)):
        try:
            setattr(owner, name, value)
        except (AttributeError, TypeError, ValueError):
            pass
    return out


def _render_result():
    for image in bpy.data.images:
        if image.type == "RENDER_RESULT":
            return image
    raise RuntimeError("Render produced no result")


def _strips(scene):
    editor = scene.sequence_editor_create()
    # Blender 5.0 renamed `sequences` to `strips`.
    return editor.strips if hasattr(editor, "strips") else editor.sequences


class RenderJob:
    """Renders, paints and writes one frame per step()."""

    def __init__(self, context, animation):
        scene = context.scene
        if scene.camera is None:
            raise RuntimeError("The scene has no active camera")
        settings = scene.paintify_live
        self.scene = scene
        self.animation = animation
        self.look = look_from_settings(settings)
        self.width, self.height = render_size(scene)
        # Scale from the full frame, as the camera-view overlay does.
        self.scale = stroke_scale(self.width, self.height, self.look.brush_size)
        if animation:
            self.frames = list(range(scene.frame_start, scene.frame_end + 1,
                                     max(1, scene.frame_step)))
            fps = scene.render.fps / scene.render.fps_base
            self.hold = hold_frames(fps, settings.fps) if settings.hold_frames else 1
        else:
            self.frames = [scene.frame_current]
            self.hold = 1
        self.movie = animation and scene.render.is_movie_format
        self.original_frame = scene.frame_current
        self.painter = Painter()
        self.tmpdir = tempfile.mkdtemp(prefix="paintify_")
        self.output = _output_scene(scene, self.width, self.height) if animation else None
        self.frame_image = None
        self.index = 0
        self.painted = None
        self.movie_frames = []
        self.last_file = None
        self.output_path = ""

    def __len__(self):
        return len(self.frames)

    def _render_source(self, frame):
        scene = self.scene
        scene.frame_set(frame)
        bpy.ops.render.render(write_still=False, scene=scene.name)
        path = os.path.join(self.tmpdir, "source.png")
        with _PngOutput(scene.render.image_settings):
            _render_result().save_render(filepath=path, scene=scene)
        image = bpy.data.images.load(path, check_existing=False)
        try:
            width, height = image.size
            pixels = np.empty(width * height * 4, dtype=np.float32)
            image.pixels.foreach_get(pixels)
        finally:
            bpy.data.images.remove(image)
        return pixels, width, height

    def _paint(self, frame):
        pixels, width, height = self._render_source(frame)
        texture = texture_from_pixels(pixels, width, height)
        self.painter.paint(texture, width, height, self.look, scale=self.scale,
                           temporal=True, frame=frame)
        painted = self.painter.read_pixels()
        painted[..., 3] = 1.0
        return painted

    def _image(self, pixels):
        height, width = pixels.shape[:2]
        image = self.frame_image
        if image is None or tuple(image.size) != (width, height):
            if image is not None:
                bpy.data.images.remove(image)
            image = self.frame_image = bpy.data.images.new(
                "Paintify Frame", width, height, alpha=True)
        image.pixels.foreach_set(pixels.ravel())
        return image

    def _write(self, frame, fresh):
        if self.movie:
            if fresh:
                self.last_file = os.path.join(self.tmpdir, f"frame_{self.index:06d}.png")
                image = self._image(self.painted)
                image.filepath_raw = self.last_file
                image.file_format = "PNG"
                image.save()
            self.movie_frames.append(self.last_file)
        else:
            path = self.scene.render.frame_path(frame=frame)
            self._image(self.painted).save_render(filepath=path, scene=self.output)
            self.output_path = path

    def step(self):
        """Processes the next frame. Returns False when every frame is done."""
        if self.index >= len(self.frames):
            return False
        frame = self.frames[self.index]
        fresh = self.painted is None or self.index % self.hold == 0
        if fresh:
            self.painted = self._paint(frame)
        if self.animation:
            self._write(frame, fresh)
        self.index += 1
        return self.index < len(self.frames)

    def _encode_movie(self):
        out = self.output
        start = self.scene.frame_start
        strip = _strips(out).new_image(name="Paintify", filepath=self.movie_frames[0],
                                       channel=1, frame_start=start)
        for path in self.movie_frames[1:]:
            strip.elements.append(os.path.basename(path))
        out.frame_start = start
        out.frame_end = start + len(self.movie_frames) - 1
        bpy.ops.render.render(animation=True, scene=out.name)
        self.output_path = out.render.frame_path(frame=start)

    def finish(self):
        """Writes what remains and returns the output: a file path for an
        animation, the result image for a still."""
        if self.animation:
            if self.movie and self.movie_frames:
                self._encode_movie()
            return self.output_path
        image = bpy.data.images.get(RESULT_IMAGE)
        height, width = self.painted.shape[:2]
        if image is None:
            image = bpy.data.images.new(RESULT_IMAGE, width, height, alpha=True)
        elif tuple(image.size) != (width, height):
            image.scale(width, height)
        image.pixels.foreach_set(self.painted.ravel())
        image.update()
        return image

    def close(self):
        """Restores the scene and removes scratch data. Safe to call twice."""
        if self.scene.frame_current != self.original_frame:
            self.scene.frame_set(self.original_frame)
        if self.frame_image is not None:
            bpy.data.images.remove(self.frame_image)
            self.frame_image = None
        if self.output is not None:
            bpy.data.scenes.remove(self.output)
            self.output = None
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        self.painter = None


def _show(context, image):
    """Shows the painted still in an Image Editor, opening the render view
    the way F12 does when none is open."""
    def find():
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    return area
        return None

    area = find()
    if area is None and not bpy.app.background:
        try:
            bpy.ops.render.view_show("INVOKE_DEFAULT")
        except RuntimeError:
            pass
        area = find()
    if area is not None:
        area.spaces.active.image = image
        area.tag_redraw()


class _JobGuard:
    active = False


class PAINTIFY_OT_render_image(bpy.types.Operator):
    bl_idname = "paintify.render_image"
    bl_label = "Render Painted Image"
    bl_description = ("Render the current frame with the scene's engine and paint it like "
                      "the viewport overlay. The result opens as the 'Paintify Render' image")

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not _JobGuard.active

    def execute(self, context):
        try:
            job = RenderJob(context, animation=False)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        try:
            job.step()
            image = job.finish()
        except Exception as exc:
            self.report({"ERROR"}, f"Paintify render failed: {exc}")
            return {"CANCELLED"}
        finally:
            job.close()
        _show(context, image)
        self.report({"INFO"}, f"Painted render in image '{image.name}'")
        return {"FINISHED"}


class PAINTIFY_OT_render_animation(bpy.types.Operator):
    bl_idname = "paintify.render_animation"
    bl_label = "Render Painted Animation"
    bl_description = ("Render the frame range, paint it like the viewport overlay and write "
                      "the scene's output (image sequence or movie). Esc cancels")

    _job = None
    _timer = None

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not _JobGuard.active

    def _start(self, context):
        try:
            self._job = RenderJob(context, animation=True)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return False
        _JobGuard.active = True
        return True

    def _end(self, context):
        _JobGuard.active = False
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            context.window_manager.progress_end()
            if context.workspace is not None:
                context.workspace.status_text_set(None)
        if self._job is not None:
            self._job.close()
            self._job = None

    def _finish(self):
        path = self._job.finish()
        self.report({"INFO"}, f"Painted animation written to {bpy.path.abspath(path)}")

    def execute(self, context):
        # Blocking path, for scripts and background mode.
        if not self._start(context):
            return {"CANCELLED"}
        try:
            while self._job.step():
                pass
            self._finish()
        except Exception as exc:
            self.report({"ERROR"}, f"Paintify render failed: {exc}")
            return {"CANCELLED"}
        finally:
            self._end(context)
        return {"FINISHED"}

    def invoke(self, context, event):
        if not self._start(context):
            return {"CANCELLED"}
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.progress_begin(0, len(self._job))
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC" and event.value == "PRESS":
            self.report({"WARNING"}, "Painted animation render cancelled")
            self._end(context)
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        job = self._job
        try:
            more = job.step()
            context.window_manager.progress_update(job.index)
            if context.workspace is not None:
                context.workspace.status_text_set(
                    f"Paintify: painted frame {job.index} of {len(job)} (Esc to cancel)")
            if more:
                return {"RUNNING_MODAL"}
            self._finish()
        except Exception as exc:
            self.report({"ERROR"}, f"Paintify render failed: {exc}")
            self._end(context)
            return {"CANCELLED"}
        self._end(context)
        return {"FINISHED"}
