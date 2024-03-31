
from tqdm import tqdm

from typing import List
import random


# find the only True value in the list
def binaryElimination(_list: List[bool]) -> int:
    left = 0
    right = len(_list) - 1

    while left < right:
        mid = (left + right) // 2
        print(f'{left:04} -> {mid:04} -> {right:04}')
        if any(_list[mid:right]):
            left = mid + 1
        else:
            right = mid - 1

    print('----------')
    print(f'{left:04} -> {mid:04} -> {right:04} => {right}')
    return right


if __name__ == '__main__':
    # for _ in [0]:
    for _ in (range(2, 5000)):
        # random_number = random.randint(1, _-1)
        random_number = random.randint(0, 1023)
        print(f'[{random_number}]')
        # random_number = 50
        # print(random_number)
        _list = [False] * 1024
        # print(_list)
        _list[random_number] = True

        result = binaryElimination(_list)
        # print()
        if result != random_number:
            # print('Failure!!')
            exit()
        print('========================================')

    print('Success!!')
