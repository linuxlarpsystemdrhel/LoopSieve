"""A deliberately failing check for the local diagnostic walkthrough."""


def average(values):
    return sum(values) / len(values)


if __name__ == "__main__":
    print(average([]))
