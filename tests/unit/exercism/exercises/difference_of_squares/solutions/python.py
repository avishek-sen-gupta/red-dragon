def square_of_sum(n):
    total = 0
    i = 1
    while i <= n:
        total = total + i
        i = i + 1
    return total * total


def sum_of_squares(n):
    total = 0
    i = 1
    while i <= n:
        total = total + i * i
        i = i + 1
    return total


def difference_of_squares(n):
    return square_of_sum(n) - sum_of_squares(n)


answer = difference_of_squares(10)
