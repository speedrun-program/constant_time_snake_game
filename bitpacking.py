
import sys

from collections.abc import Iterable, Iterator
try: # typing.Self isn't available before 3.11
    from typing import Optional, Self, Tuple, Union
except ImportError:
    from typing import Optional, Tuple, Union

IS_AT_LEAST_3DOT11 = sys.version_info.major > 3 or (sys.version_info.major == 3 and sys.version_info.minor >= 11)

# a class which lets you use a byte array as if it was an arbitrarily deeply nested
# array with each index being any number of bits wide
class BitPackingArray:
    def __init__(
            self,
            dimensions: Union[Iterable[int], int],
            bits_per_index: int,
            bytearrayview: Optional[memoryview] = None,
            start_bit_offset: int = 0,
            current_dimension: int = 0) -> None:
        self.bits_per_index = bits_per_index
        self.dimensions = tuple(map(int, dimensions)) if not isinstance(dimensions, int) else (dimensions,)
        
        if len(self.dimensions) == 1 and self.dimensions[0] == 0:
            self.byte_array = bytearray(0)
            self.start_bit_offset = 0
            self.current_dimension = 0
            return
        
        if bytearrayview is None:
            if any(d <= 0 for d in self.dimensions):
                raise ValueError("all dimensions must be greater than 0")
            elif bits_per_index <= 0:
                raise ValueError("bits_per_index must be greater than 0")
            elif not dimensions:
                raise ValueError("no dimensions given")
            
            total_bits = bits_per_index
            for d in self.dimensions:
                total_bits *= d
            
            total_bytes = (total_bits // 8) + (total_bits % 8 != 0)
            self.byte_array = bytearray(total_bytes)
        else:
            self.byte_array = bytearrayview
        self.start_bit_offset = start_bit_offset
        self.current_dimension = current_dimension
    
    
    # error checks indexes and turns negative indexes into normal indexes
    def index_generator(self, position: Iterable[int]) -> Iterator[int]:
        for depth, (pos, dimension_length) in enumerate(zip(position, self.dimensions)):
            actual_position = pos if pos >= 0 else dimension_length + pos
            if not 0 <= actual_position < dimension_length:
                raise IndexError(f"attempted to access index {pos} of dimension {depth}, which is length {dimension_length}")
            
            yield actual_position
    
    
    # finds byte position and bit position of data being accessed
    def get_actual_position(self, position: Union[Iterable[int], int]) -> Tuple[int, int]: # returns (start_byte, start_bit)
        if isinstance(position, int):
            position = (position,)
        if (len(position) != len(self.dimensions)):
            raise ValueError(
                f"position argument had {len(position)} dimensions, "
                f"but self.dimensions has {len(self.dimensions)} dimensions"
            )
        
        index_generator = self.index_generator(position)
        which_bit = next(index_generator)
        for i, pos in enumerate(index_generator, 1):
            which_bit = (which_bit * self.dimensions[i]) + pos
        which_bit *= self.bits_per_index
        which_bit += self.start_bit_offset
        
        return divmod(which_bit, 8)
    
    
    def get(self, position: Union[Iterable[int], int]) -> int:
        which_byte, byte_start_position = self.get_actual_position(position)
        bits_left_to_read = self.bits_per_index
        current_bit_position = min(8 - byte_start_position, bits_left_to_read)
        
        # reading first byte
        value = (self.byte_array[which_byte] >> byte_start_position) & ((1 << current_bit_position) - 1)
        bits_left_to_read -= current_bit_position
        which_byte += 1
        
        # reading middle byte(s)
        while bits_left_to_read >= 8:
            value += self.byte_array[which_byte] << current_bit_position
            bits_left_to_read -= 8
            current_bit_position += 8
            which_byte += 1
        
        #reading last byte
        if bits_left_to_read > 0:
            value += (self.byte_array[which_byte] & ((1 << bits_left_to_read) - 1)) << current_bit_position
        
        assert 0 <= value < 1 << self.bits_per_index, f"return value {value} out of range(0, {1 << self.bits_per_index})"
        return value
    
    
    def set(self, position: Union[Iterable[int], int], new_value: int) -> None:
        which_byte, byte_start_position = self.get_actual_position(position)
        bits_left_to_set = self.bits_per_index
        
        # setting first byte
        bits_left_in_first_byte = min(8 - byte_start_position, bits_left_to_set)
        first_byte_start_bits = self.byte_array[which_byte] & ((1 << byte_start_position) - 1)
        current_value_to_write = new_value & ((1 << bits_left_in_first_byte) - 1)
        self.byte_array[which_byte] >>= byte_start_position + bits_left_in_first_byte
        self.byte_array[which_byte] <<= bits_left_in_first_byte
        self.byte_array[which_byte] += current_value_to_write
        self.byte_array[which_byte] <<= byte_start_position
        self.byte_array[which_byte] += first_byte_start_bits
        new_value >>= bits_left_in_first_byte
        bits_left_to_set -= bits_left_in_first_byte
        which_byte += 1
        
        # setting middle byte(s)
        while bits_left_to_set >= 8:
            current_value_to_write = new_value & 0b11111111
            self.byte_array[which_byte] = current_value_to_write
            new_value >>= 8
            bits_left_to_set -= 8
            which_byte += 1
        
        # setting last byte
        if bits_left_to_set > 0:
            self.byte_array[which_byte] >>= bits_left_to_set
            self.byte_array[which_byte] <<= bits_left_to_set
            self.byte_array[which_byte] += new_value
    
    
    def __getitem__(self, idx: int) -> Union[Self if IS_AT_LEAST_3DOT11 else None, int]:
        actual_idx = idx if idx >= 0 else self.dimensions[0] + idx
        if not 0 <= actual_idx < self.dimensions[0]:
            raise IndexError(f"attempted to get index {idx} of dimension {self.current_dimension}, which is length {self.dimensions[0]}")
        
        if len(self.dimensions) == 1:
            return self.get(idx)
        
        new_dimensions = self.dimensions[1:]
        
        bits_per_outer_index = self.bits_per_index
        for d in new_dimensions:
            bits_per_outer_index *= d
        
        start_bit = (bits_per_outer_index * actual_idx) + self.start_bit_offset
        stop_bit = (bits_per_outer_index * (actual_idx + 1)) + self.start_bit_offset
        start_byte, start_byte_bit_offset = divmod(start_bit, 8)
        stop_byte = (stop_bit // 8) + (stop_bit % 8 != 0)
        bytearrayview = memoryview(self.byte_array)[start_byte:stop_byte]
        
        return BitPackingArray(new_dimensions, self.bits_per_index, bytearrayview, start_byte_bit_offset, self.current_dimension + 1)
    
    
    def __setitem__(self, idx: int, new_value: int) -> None:
        if len(self.dimensions) > 1:
            raise ValueError("__setitem__ only supported on 1-dimensional arrays, len(self.dimensions) must be 1")
        if not 0 <= (idx if idx >= 0 else self.dimensions[0] + idx) < self.dimensions[0]:
            raise IndexError(f"attempted to set index {idx} of dimension {self.current_dimension}, which is length {self.dimensions[0]}")
        if not 0 <= new_value < 1 << self.bits_per_index:
            raise ValueError(f"value must be in range(0, {1 << self.bits_per_index}), value was {new_value}")
        
        self.set(idx, new_value)
    
    
    def append(self, new_value: int) -> None:
        if len(self.dimensions) > 1 or self.current_dimension > 0:
            raise ValueError("appending only supported on 1-dimensional arrays")
        if not 0 <= new_value < 1 << self.bits_per_index:
            raise ValueError(f"value must be in range(0, {1 << self.bits_per_index}), value was {new_value}")
        
        # allocating more space if necessary
        total_bits = self.bits_per_index * (self.dimensions[0] + 1)
        total_bytes = (total_bits // 8) + (total_bits % 8 != 0)
        while len(self.byte_array) < total_bytes:
            self.byte_array.append(0)
        
        self.dimensions = ((self.dimensions[0] + 1),)
        self.set(-1, new_value)
    
    
    def reshape(self, dimensions: Union[Iterable[int], int], bits_per_index: int) -> None:
        if isinstance(self.byte_array, memoryview):
            raise ValueError("can only reshape entire BitPackingArray")
        
        dimensions = tuple(map(int, dimensions)) if not isinstance(dimensions, int) else (dimensions,)
        
        if len(dimensions) == 1 and dimensions[0] == 0:
            self.byte_array.__init__(0)
            self.bits_per_index = bits_per_index
            self.dimensions = dimensions
            return
        
        if any(d <= 0 for d in dimensions):
            raise ValueError("all dimensions must be greater than 0")
        elif bits_per_index <= 0:
            raise ValueError("bits_per_index must be greater than 0")
        elif not dimensions:
            raise ValueError("no dimensions given")
        
        total_bits = bits_per_index
        for d in dimensions:
            total_bits *= d
        total_bytes = (total_bits // 8) + (total_bits % 8 != 0)
        
        self.byte_array.__init__(total_bytes) # attempt this first in case memory can't be allocated
        self.bits_per_index = bits_per_index
        self.dimensions = dimensions


if not IS_AT_LEAST_3DOT11:
    BitPackingArray.__getitem__.__annotations__["return"] = Union[BitPackingArray, int]
