#this is just a quick test to make sure the pipeline works!
from tqdm import tqdm

from typing import List
import random


# find the first True value in the list
def binaryElimination(_list: List[bool]) -> int:
    left = 0
    right = len(_list) - 1

    while left <= right:
        mid = (left + right) // 2
        if any(_list[left:mid + 1]):
            right = mid - 1
        else:
            left = mid + 1

    return right + 1


if __name__ == '__main__':
    _list = [False] * 1024
    for _ in tqdm(range(0, 5000000)):
        random_number = random.randint(0, 1023)
        _list[random_number] = True
        result = binaryElimination(_list)

        if result != random_number:
            print(f'Failure!! {result}')
            exit()

        _list[random_number] = False
    print('Success!!')
