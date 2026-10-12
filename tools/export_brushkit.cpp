#include "styles.h"
#include <iomanip>
#include <iostream>

void block(const StyleParams& style) {
    const float* values = reinterpret_cast<const float*>(&style);
    std::cout << '[';
    for (size_t i = 0; i < sizeof(style) / sizeof(float); ++i) {
        if (i) std::cout << ',';
        std::cout << values[i];
    }
    std::cout << ']';
}

int main() {
    std::cout << std::setprecision(9) << "{\"defaults\":";
    block(StyleParams{});
    std::cout << ",\"brushes\":[";
    const auto& entries = styles::list();
    for (size_t i = 0; i < entries.size(); ++i) {
        if (i) std::cout << ',';
        StyleParams style;
        styles::applyBrushTexture(int(i), style);
        std::cout << "{\"key\":\"" << entries[i].key << "\",\"name\":\""
                  << entries[i].name << "\",\"era\":\"" << entries[i].era
                  << "\",\"values\":";
        block(style);
        std::cout << '}';
    }
    std::cout << "]}";
}
