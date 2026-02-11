import argparse

import matplotlib.pyplot as plt

from .stuff import gen_data


def create_figure(path: str):
    # Create sample data
    x, y = gen_data()

    # Create the figure
    plt.figure(figsize=(8, 6))
    plt.plot(x, y, "b-", label="sin(x)")
    plt.title("Example Sine Wave")
    plt.xlabel("x")
    plt.ylabel("sin(x)")
    plt.grid(True)
    plt.legend()

    # Save the figure
    plt.savefig(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()

    create_figure(args.output)


if __name__ == "__main__":
    main()
