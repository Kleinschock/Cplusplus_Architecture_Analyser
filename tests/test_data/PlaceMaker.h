#pragma once

class PlaceMaker {
public:
    PlaceMaker();
    ~PlaceMaker();

    void doSomething(int x);
    int getValue() const;

private:
    int m_value;
};
