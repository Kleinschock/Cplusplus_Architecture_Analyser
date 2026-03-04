#include "PlaceMaker.h"

PlaceMaker::PlaceMaker() : m_value(0) {
}

PlaceMaker::~PlaceMaker() {
}

void PlaceMaker::doSomething(int x) {
    m_value += x;
}

int PlaceMaker::getValue() const {
    return m_value;
}
