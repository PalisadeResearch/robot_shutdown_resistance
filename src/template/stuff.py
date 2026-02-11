import numpy as np


def gen_data():
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    return x, y
