enum class Noise {
    Perlin,
    Simplex,
    White
};

class NoiseGenerator {
public:
    void applyNoise(Noise type) {
        switch (type) {
            case Noise::Perlin:
                // Apply Perlin
                break;
            case Noise::Simplex:
                // Apply Simplex
                break;
            case Noise::White:
                // Apply White
                break;
            default:
                break;
        }
    }
};
