
from attrs import define

from typing import cast, List
import sys
import re


class BadVersionString(ValueError): pass
class ValidationFailure(Exception): pass

VERSION_DELIMITERS = ['+', '_', ':']

@define
class VersionPart:
    components: List[int]

    def __str__(self) -> str:
        return '.'.join([str(x) for x in self.components])
    
    def __repr__(self):
        return self.__str__()

    def __eq__(self, other: 'VersionPart') -> bool: # type: ignore[override]
        for i in range(max(len(self.components), len(other.components))):
            a = self.components[i] if len(self.components) > i else 0
            b = other.components[i] if len(other.components) > i else 0
            if a < b:
                return False
            elif a > b:
                return False
        return True
    
    def __lt__(self, other: 'VersionPart') -> bool:
        for i in range(max(len(self.components), len(other.components))):
            a = self.components[i] if len(self.components) > i else 0
            b = other.components[i] if len(other.components) > i else 0
            if a < b:
                return True
            elif a > b:
                return False
        return False
    
    def __le__(self, other: 'VersionPart') -> bool:
        for i in range(max(len(self.components), len(other.components))):
            a = self.components[i] if len(self.components) > i else 0
            b = other.components[i] if len(other.components) > i else 0
            if a < b:
                return True
            elif a > b:
                return False
        return True
    
    def __gt__(self, other: 'VersionPart') -> bool:
        for i in range(max(len(self.components), len(other.components))):
            a = self.components[i] if len(self.components) > i else 0
            b = other.components[i] if len(other.components) > i else 0
            if a > b:
                return True
            elif a < b:
                return False
        return False
    
    def __ge__(self, other: 'VersionPart') -> bool:
        for i in range(max(len(self.components), len(other.components))):
            a = self.components[i] if len(self.components) > i else 0
            b = other.components[i] if len(other.components) > i else 0
            if a > b:
                return True
            elif a < b:
                return False
        return True

@define
class Version:
    text: str
    parts: List[VersionPart] = []

    def __str__(self) -> str:
        if self.text != "*":
            return '-'.join([str(part) for part in self.parts])
        else:
            return "*"
    
    def __repr__(self):
        return self.__str__()

    @classmethod
    def fromString(cls, text_raw: str) -> 'Version':
        if text_raw in ["", "*"]:
            return cls("*")

        text = text_raw.lower()
        text = text.replace('alpha', '0')
        text = text.replace('beta', '1')
        text = text.replace('pre-release', '2')
        text = text.replace('pre', '2')
        text = text.replace('rc', '2')
        text = text.replace('snapshot', '2')
        text = text.replace('release', '3')

        for DELIMITER in VERSION_DELIMITERS:
            text = text.replace(DELIMITER, '-')

        valid_parts = []
        part_candidates = text.split('-')
        for candidate in part_candidates:
            if candidate == '':
                continue

            # disallow candidates that are:
            #   - text-only
            #   - commit refs
            if re.fullmatch(r'(?!\.)[0-9]*[a-z]+[0-9a-z]*$', candidate):
                continue

            elif re.fullmatch(r'^[a-z0-9.]+$', candidate):
                for word in re.findall(r'[.]*([a-z]+[.]+)', candidate):
                    candidate = candidate.replace(word, '')

                for letter in re.findall(r'[0-9]([a-z])', candidate):
                    letter = cast(str, letter)
                    idx = ord(letter) - ord('a') + 1
                    candidate = candidate.replace(f'{letter}', f'.{idx}')

                for letter in re.findall(r'([a-z])', candidate):
                    letter = cast(str, letter)
                    idx = ord(letter) - ord('a') + 1
                    candidate = candidate.replace(f'{letter}', f'{idx}')

                valid_parts.append(candidate)

        if len(valid_parts) > 0:
            return cls(text, [VersionPart([int(x) for x in components.split('.') if x != '']) for components in valid_parts])
            
        raise BadVersionString(f"Invalid version string '{text}'")

    def __eq__(self, other: 'Version') -> bool: # type: ignore[override]
        for i in range(max(len(self.parts), len(other.parts))):
            a = self.parts[i] if len(self.parts) > i else VersionPart([0])
            b = other.parts[i] if len(other.parts) > i else VersionPart([0])
            if a < b:
                return False
            elif a > b:
                return False
        return True
    
    def __lt__(self, other: 'Version') -> bool:
        for i in range(max(len(self.parts), len(other.parts))):
            a = self.parts[i] if len(self.parts) > i else VersionPart([0])
            b = other.parts[i] if len(other.parts) > i else VersionPart([0])
            if a < b:
                return True
            elif a > b:
                return False
        return False
    
    def __le__(self, other: 'Version') -> bool:
        for i in range(max(len(self.parts), len(other.parts))):
            a = self.parts[i] if len(self.parts) > i else VersionPart([0])
            b = other.parts[i] if len(other.parts) > i else VersionPart([0])
            if a < b:
                return True
            elif a > b:
                return False
        return True
    
    def __gt__(self, other: 'Version') -> bool:
        for i in range(max(len(self.parts), len(other.parts))):
            a = self.parts[i] if len(self.parts) > i else VersionPart([0])
            b = other.parts[i] if len(other.parts) > i else VersionPart([0])
            if a > b:
                return True
            elif a < b:
                return False
        return False
    
    def __ge__(self, other: 'Version') -> bool:
        for i in range(max(len(self.parts), len(other.parts))):
            a = self.parts[i] if len(self.parts) > i else VersionPart([0])
            b = other.parts[i] if len(other.parts) > i else VersionPart([0])
            if a > b:
                return True
            elif a < b:
                return False
        return True

@define
class VersionRangePart:
    bound: Version
    inclusive: bool

@define
class VersionRange:
    lower: VersionRangePart
    upper: VersionRangePart

    def __str__(self) -> str:
        if self.upper.bound.text == "*" and self.lower.bound.text == "*":
            return "*"
        else:
            return ('[' if self.lower.inclusive else '(') + f'{self.lower.bound},{self.upper.bound}' + (']' if self.upper.inclusive else ')')

    def __repr__(self):
        return self.__str__()
    
    def contains(self, version: Version) -> bool:
        result = True
        
        if self.lower.bound.text == "*":
            pass
        elif self.lower.inclusive:
            comp = (self.lower.bound <= version)
            result = result and comp
        else:
            comp = (self.lower.bound < version)
            result = result and comp

        if self.upper.bound.text == "*":
            pass
        elif self.upper.inclusive:
            comp = (self.upper.bound >= version)
            result = result and comp
        else:
            comp = (self.upper.bound > version)
            result = result and comp

        return result

    @classmethod
    def fromString(cls, range_raw: str) -> List['VersionRange']:
        ranges: List['VersionRange'] = []

        if range_raw in ["*", ","]:
            return [cls(VersionRangePart(Version.fromString("*"), True), VersionRangePart(Version.fromString("*"), True))]
        elif re.fullmatch(r'^[a-zA-Z0-9-+:_.]+$', range_raw):
            vrp = VersionRangePart(Version.fromString(range_raw), True)
            return [cls(vrp, vrp)]

        found = False
        for range in re.findall(r'([\[\(][0-9a-zA-Z+-_:., ]*[\]\)])', range_raw):
            found = True
            parts = range.split(',')
            lower = parts[0].strip()

            if len(parts) > 1:
                upper = parts[1].strip()
            else:
                upper = lower

            if lower in ['(', '[']:
                lower = lower + '*'
            if upper in [']', ')']:
                upper = '*' + upper

            lower_part = VersionRangePart(Version.fromString(lower.strip('[]()')), lower[0]  == '[')
            upper_part = VersionRangePart(Version.fromString(upper.strip('[]()')), upper[-1] == ']')
            ranges.append(VersionRange(lower_part, upper_part))

        if not found:
            raise BadVersionString(f"Could not form from '{range_raw}'")

        return ranges


def test():
    a = Version.fromString('1.20.2+forge+0.1')
    b = Version.fromString('1.20.3_forge_0.3.5a')
    c = Version.fromString('1.20.3-neoforge-0.3.5c')
    d = Version.fromString('1.20.4-neoforge-1.0.0a')
    print('===========================================================')
    print(a)
    print(b)
    print(("[PASS]" if a <  b else "[FAIL]") + ": <" )
    print(("[PASS]" if a <= b else "[FAIL]") + ": <=")
    print(("[PASS]" if not a >  b else "[FAIL]") + ": >" )
    print(("[PASS]" if not a >= b else "[FAIL]") + ": >=")
    print(("[PASS]" if not a == b else "[FAIL]") + ": ==")
    print('===========================================================')
    print(a)
    print(c)
    print(("[PASS]" if a <  c else "[FAIL]") + ": <" )
    print(("[PASS]" if a <= c else "[FAIL]") + ": <=")
    print(("[PASS]" if not a >  c else "[FAIL]") + ": >" )
    print(("[PASS]" if not a >= c else "[FAIL]") + ": >=")
    print(("[PASS]" if not a == c else "[FAIL]") + ": ==")
    print('===========================================================')
    print(a)
    print(d)
    print(("[PASS]" if a <  d else "[FAIL]") + ": <"    )
    print(("[PASS]" if a <= d else "[FAIL]") + ": <="   )
    print(("[PASS]" if not a >  d else "[FAIL]") + ": >"    )
    print(("[PASS]" if not a >= d else "[FAIL]") + ": >="   )
    print(("[PASS]" if not a == d else "[FAIL]") + ": =="   )
    print('===========================================================')
    ab = VersionRange(VersionRangePart(a, True), VersionRangePart(b, True))
    ac = VersionRange(VersionRangePart(a, True), VersionRangePart(c, True))
    bc = VersionRange(VersionRangePart(b, True), VersionRangePart(c, True))
    print(ab)
    print(a)
    print('[PASS]' if ab.contains(a) else '[FAIL]')
    print('===========================================================')
    print(ab)
    print(b)
    print('[PASS]' if ab.contains(b) else '[FAIL]')
    print('===========================================================')
    print(ab)
    print(c)
    print('[PASS]' if not ab.contains(c) else '[FAIL]')
    print('===========================================================')
    print(ac)
    print(b)
    print('[PASS]' if ac.contains(b) else '[FAIL]')
    print('===========================================================')
    print(bc)
    print(a)
    print('[PASS]' if not bc.contains(a) else '[FAIL]')
    print('===========================================================')



if __name__ == '__main__':
    test()

