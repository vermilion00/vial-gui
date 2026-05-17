import struct 
import math
from protocol.base_protocol import BaseProtocol

AM_PREFIX = 0xFD
# Analog matrix transactions
AM_GET_KEYBOARD_DEF = 0x00
AM_GET_KEYBOARD_DATA = 0x01
AM_GET_MATRIX_TO_NUM = 0x02
AM_GET_SWITCH_VALUE = 0x03
AM_SET_SWITCH_HEIGHT = 0x04
AM_SET_SWITCH_MODE = 0x05
AM_SET_SWITCH_PRIORITY = 0x06
AM_SET_PROFILE_LAYERS = 0x07
AM_SET_PROFILE_CONFIG = 0x08
AM_SET_PRIORITY_CONFIG = 0x09
AM_SET_DYNAMIC_CALIBRATION = 0x0A
AM_SET_DEADZONE = 0x0B
AM_SET_SAVE_PROFILE_LOCK = 0x0C
AM_SET_USED_PROFILES = 0x0D
AM_SET_ACTIVE_PROFILE = 0x0E
AM_SAVE_CONFIG = 0x0F
AM_CLEAR_CALIBRATION_DATA = 0x10
AM_RESET_KEYBOARD_DATA = 0x11
# AM_GET_KEYBOARD_DEF subtransactions
AM_GET_DEF = 0x00
AM_GET_PROFILE = 0x01
AM_GET_CALIBRATION_DATA = 0x02

LOW_RES_MULT = 50
HIGH_RES_MULT = 1000
MULT_MULT = 100

SWITCH_PRESS_HEIGHT = 0
SWITCH_RELEASE_HEIGHT = 1
SWITCH_PRESS_DISTANCE = 2
SWITCH_RELEASE_DISTANCE = 3
SWITCH_MODE = 4
SWITCH_PRIORITY = 5

HEIGHT_TO_INDEX = {
    'trigger_height': 0,
    'release_height': 1,
    'rt_press': 2,
    'rt_release': 3
}

DC_TO_INDEX = {
    'dc_switch_num': 0,
    'dc_factor': 1,
    'dc_delta': 2
}

DEADZONE_TO_INDEX = {
    'top_deadzone': 0,
    'bottom_deadzone': 1,
    'smoothing': 2,
    'top_mult': 3,
    'right_mult': 4,
    'slave_mult': 5,
    'right_filter': 6, # Not implemented
    'slave_filter': 7, # Not implemented
    'top_joystick_deadzone': 8,
    'bottom_joystick_deadzone': 9,
}

HIGHEST_QSID = 20
class ProtocolAnalogMatrix(BaseProtocol):
    def __init__(self):
        self.am_enabled = False
        self.heights = {}
        self.modes = []
        self.am_config = {}
        self.am_settings = {}
        self.setting_values = [0 for _ in range(HIGHEST_QSID)]
        self.priority_status = []
        self.profile_layers = []
        self.profile_switch_mode = 0
        self.index = 255
        self.am_profile = 0
        self.profiles = 0
        self.max_profiles = 0
        self.am_def_size = 0
        self.matrix_to_num = []
        self.num_to_matrix = []
        self.am_height_mult = LOW_RES_MULT
        self.switch_value = 0
        # Bootloader, Calibration, Clear EEPROM, Clear calibration
        self.init_mode_num = [0, 0, 0, 0]

    #MARK: Get def
    # Get the size of the configuration struct and the state of all features
    def get_keyboard_def(self):
        data = self.usb_send(self.dev, struct.pack("BBB", AM_PREFIX, AM_GET_KEYBOARD_DEF, AM_GET_DEF), retries=20)

        # If the first byte has changed, it means the command wasn't handled
        if data[0] != AM_PREFIX:
            return False

        self.am_def_size = data[2] | (data[3] << 8)

        #TODO: Consolidate some stuff, what do I put where?
        #      It would make sense to put stuff I change in GUI as properties, and the rest in the config
        self.am_config = {
            'use_trigger_height': True if data[4] & 1 else False,
            'use_rt_distance': True if data[4] & (1 << 1) else False,
            'use_none': True if data[4] & (1 << 2) else False,
            'use_rapid_trigger': True if data[4] & (1 << 3) else False,
            'use_continuous_rapid_trigger': True if data[4] & (1 << 4) else False,
            'use_constant_rapid_trigger': True if data[4] & (1 << 5) else False,
            'dynamic_calibration': True if data[5] & 1 else False,
            'priority_mode': True if data[5] & (1 << 1) else False,
            'priority_indices': True if data[5] & (1 << 6) else False,
            'mixed_matrix': True if data[5] & (1 << 2) else False,
            'adjustable_filter_strength': True if data[5] & (1 << 3) else False,
            'invert_adc': True if data[5] & (1 << 4) else False,
            'distance_from_bottom': True if data[5] & (1 << 5) else False,
            'joystick': True if data[6] & 1 else False,
            'midi': True if data[6] & (1 << 1) else False,
            'split_keyboard': True if data[6] & (1 << 2) else False,
            'init_keys': True if data[6] & (1 << 3) else False,
            'use_high_resolution': True if data[4] & (1 << 6) else False,
            'max_profiles': data[8],
            'save_profile_lock': True if data[9] & (1 << 6) else False,
            'total_switch_num': data[10],
            'switch_num': data[11],
            'switch_num_r': data[10] - data[11],
            'rc_switch_num': data[12],
            'layer_size': data[13], # Size of layer_state_t in bytes
            #TODO: Implement this
            'filter_strength': 0,
            'right_filter_strength': 0,
            'slave_filter_strength': 0,
            'matrix_rows': data[14],
            'matrix_cols': data[15],
            'travel_distance': (data[16] | data[17] << 8) / 100,
        }

        self.profiles = data[9] & 0b00001111
        self.max_profiles = data[8]
        self.am_profile = data[18]
        self.am_height_mult = HIGH_RES_MULT if self.am_config['use_high_resolution'] else LOW_RES_MULT

        # All enabled options for the settings tab
        self.am_settings = {
            'profiles': {'title': 'Profiles', 'type': 'divider'},
            'default_profile': {'title': 'Default profile', 'type': 'integer', 'min': 0, 'max': self.profiles, 'width': 1, 'qsid': 0},
            'profile_switch_mode': {'title': 'Profile switch mode', 'type': 'combo', 'options': ('Default profile', 'Last profile', 'Manual'), 'qsid': 1},
            'deadzone_divider': {'title': 'Deadzones', 'type': 'divider'},
            'top_deadzone': {'title': 'Top deadzone', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 2},
            'bottom_deadzone': {'title': 'Bottom deadzone', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 3},
            'smoothing': {'title': 'Smoothing', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 4},
            'top_mult': {'title': 'Top deadzone multiplier', 'type': 'float', 'min': 1.0, 'max': 3.55, 'step': 0.01, 'width': 1, 'qsid': 5},
        }

        # Add additional settings based on enabled features
        if self.am_config['split_keyboard']:
            # self.settings['mult_label'] = {'title': 'Split Multipliers', 'type': 'divider'}
            self.am_settings['right_mult'] = {'title': 'Right multiplier', 'type': 'float', 'min': 0, 'max': 2.55, 'step': 0.01, 'width': 1, 'qsid': 6}
            self.am_settings['slave_mult'] = {'title': 'Slave multiplier', 'type': 'float', 'min': 0, 'max': 2.55, 'step': 0.01, 'width': 1, 'qsid': 7}
            
        if self.am_config['adjustable_filter_strength']:
            self.am_settings['filter_strength'] = {'title': 'Filter strength', 'type': 'integer', 'min': 0, 'max': 5, 'width': 1, 'qsid': 8}
            if self.am_config['split_keyboard']:
                # self.am_settings['right_filter_strength'] = {'title': 'Right filter strength', 'type': 'integer', 'min': 0, 'max': 5, 'width': 1, 'qsid': 9}
                self.am_settings['slave_filter_strength'] = {'title': 'Slave filter strength', 'type': 'integer', 'min': 0, 'max': 5, 'width': 1, 'qsid': 10}

        if self.am_config['priority_mode']:
            self.am_settings['prio_label'] = {'title': 'Priority', 'type': 'divider'}
            #TODO: Add prio profile buttons here
            self.am_settings['priority_profiles'] = {'title': 'Priority profiles', 'type': 'bitmap', 'min': 0, 'max': self.profiles, 'width': 2, 'qsid': 11}

            if self.am_config['priority_indices']:
                self.am_settings['priority_level'] = {'title': 'Priority level', 'type': 'integer', 'min': 0, 'max': 10, 'width': 1, 'qsid': 12}

        if self.am_config['dynamic_calibration']:
            self.am_settings['dynamic_calibration'] = {'title': 'Dynamic Calibration', 'type': 'divider'}
            self.am_settings['dc_switch_num'] = {'title': 'Switch amount', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 13}
            self.am_settings['dc_delta'] = {'title': 'Delta', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 14}
            self.am_settings['dc_factor'] = {'title': 'Factor', 'type': 'float', 'min': 0, 'max': 0.5, 'step': 0.01, 'width': 1, 'qsid': 15}
        
        if self.am_config['joystick']:
            self.am_settings['joystick'] = {'title': 'Joystick', 'type': 'divider'}
            self.am_settings['top_joystick_deadzone'] = {'title': 'Top deadzone', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 16}
            self.am_settings['bottom_joystick_deadzone'] = {'title': 'Bottom deadzone', 'type': 'integer', 'min': 0, 'max': 255, 'width': 1, 'qsid': 17}

        self.setting_values = [0 for _ in range(HIGHEST_QSID)]
        self.saved_values = [0 for _ in range(HIGHEST_QSID)]

        return True


    #MARK: Get data
    # Get the full contents of the am_keyboard_t struct
    # Since it's not packed, a padding byte check is performed before reading any element larger than 1 byte
    # This implementation assumes that the padding bytes are placed just before the element needing alignment
    #TODO: Make sure that behavior is consistent across QMK, and add a separate option here if not
    def get_keyboard_data(self):
        parsed_len = 0
        data = b''
        for page in range(math.ceil(self.am_def_size / 32)):
            curr_data = self.usb_send(self.dev, struct.pack("<BBH", AM_PREFIX, AM_GET_KEYBOARD_DATA, page), retries=20)
            data += curr_data
        
        expected_size = math.ceil(self.am_def_size / 32) * 32
        if len(data) != expected_size: print("WARNING: The length of the transferred data doesn't match the expected length!")
        data = data[:self.am_def_size]
        full_data = data

        height_size = 2 if self.am_config['use_high_resolution'] else 1
        total_switch_num = self.am_config['total_switch_num']
        max_profiles = self.am_config['max_profiles'] # We get the max amount of profiles instead of the set profiles, as the max is always reserved
        unpack_char = 'H' if self.am_config['use_high_resolution'] else 'B'
        unpack_str = '<' + ''.join([unpack_char for _ in range(total_switch_num)])
        profile_size = height_size * total_switch_num 

        # Unpack the height values
        heights_dict = {}
        for height_type in ['trigger_height', 'release_height', 'rt_press', 'rt_release']:
            if height_type in ['trigger_height', 'release_height'] and self.am_config['use_trigger_height'] == False:
                heights_dict[height_type] = []
            elif height_type in ['rt_press', 'rt_release'] and self.am_config['use_rt_distance'] == False:
                heights_dict[height_type] = []
            else:
                heights = [list(struct.unpack(unpack_str, data[profile_size * profile_idx : profile_size * (profile_idx + 1)])) for profile_idx in range(max_profiles)]
                # Convert the compressed values to floats
                heights_dict[height_type] = [[height/self.am_height_mult for height in profile] for profile in heights]
                parsed_len += max_profiles * profile_size
                data = full_data[parsed_len:]
        self.heights = heights_dict

        # Unpack the key modes
        unpack_str = '>' + ''.join(['B' for _ in range(total_switch_num)])
        self.modes = [list(struct.unpack(unpack_str, data[profile_size * profile_idx : profile_size * (profile_idx + 1)])) for profile_idx in range(max_profiles)]
        # Get the priority status
        self.priority_status = [[(mode & 0b10000000) >> 7 for mode in profile] for profile in self.modes]
        # Mask the priority status
        self.modes = [[mode & 0x0F for mode in profile] for profile in self.modes]
        parsed_len += max_profiles * profile_size
        data = full_data[parsed_len:]

        # Unpack the rest of the config
        profile_num, profile_config = struct.unpack('BB', data[:2])
        self.am_config['default_profile'] = profile_config >> 4
        self.am_config['profile_switch_mode'] = profile_config & 0b00001111
        parsed_len += 2
        data = full_data[parsed_len:]

        if self.am_config['layer_size'] == 4:
            unpack_char = 'I' 
        elif self.am_config['layer_size'] == 2:
            unpack_char = 'H'
        else:
            unpack_char = 'B'

        # Remove padding bytes, if they're sent
        parsed_len += parsed_len % self.am_config['layer_size']
        data = full_data[parsed_len:]

        unpack_str = '<' + ''.join([unpack_char for _ in range(max_profiles)])
        self.profile_layers = list(struct.unpack(unpack_str, data[:self.am_config['layer_size'] * max_profiles]))
        parsed_len += self.am_config['layer_size'] * max_profiles
        data = full_data[parsed_len:]

        if self.am_config['priority_mode']:
            # Cut out a potential padding byte
            parsed_len += parsed_len % 2
            data = full_data[parsed_len:]
            self.am_config['priority_profiles'] = struct.unpack('H', data[:2])[0]
            parsed_len += 2
            data = full_data[parsed_len:]

            if self.am_config['priority_indices']:
                print("Test")
                self.am_config['priority_level'] = struct.unpack('B', data[:1])[0]
                parsed_len += 1
                data = full_data[parsed_len:]

        if self.am_config['dynamic_calibration']:
            data = struct.unpack('BBB', data[:3])
            self.am_config['dc_switch_num'] = data[0]
            self.am_config['dc_factor'] = data[1] / MULT_MULT # The factor is saved as a uint8_t on the keyboard
            self.am_config['dc_delta'] = data[2]
            parsed_len += 3
            data = full_data[parsed_len:]

        data = struct.unpack('BBBB', data[:4])
        self.am_config['top_deadzone'] = data[0]
        self.am_config['bottom_deadzone'] = data[1]
        self.am_config['smoothing'] = data[2]
        self.am_config['top_mult'] = data[3] / MULT_MULT
        parsed_len += 4
        data = full_data[parsed_len:]

        if self.am_config['split_keyboard']:
            self.am_config['right_mult'] = struct.unpack('B', data[:1])[0] / MULT_MULT
            self.am_config['slave_mult'] = struct.unpack('B', data[1:2])[0] / MULT_MULT
            parsed_len += 2
            data = full_data[parsed_len:]
            if self.am_config['adjustable_filter_strength']:
                self.am_config['right_filter_strength'] = struct.unpack('B', data[0:1])[0] & 0x0F
                self.am_config['slave_filter_strength'] = (struct.unpack('B', data[0:1])[0] & 0xF0) >> 4
                parsed_len += 1
                data = full_data[parsed_len:]

        if self.am_config['adjustable_filter_strength']:
            self.am_config['filter_strength'] = struct.unpack('B', data[:1])[0]
            parsed_len += 1
            data = full_data[parsed_len:]

        if self.am_config['joystick']:
            self.am_config['top_joystick_deadzone'] = struct.unpack('B', data[:1])[0]
            self.am_config['bottom_joystick_deadzone'] = struct.unpack('B', data[1:2])[0]
            parsed_len += 2
            data = full_data[parsed_len:]

        parsed_len += parsed_len % 2
        data = full_data[parsed_len:]
        self.keyboard_def_size = struct.unpack('<H', data[:2])[0] # Even though this should be the end of the array, use a slice just in case it's wrong
        if len(full_data) != self.keyboard_def_size:
            print("WARNING: The size of the transferred definition doesn't equal the keyboard definition size!")

        # Assign the setting values
        for key, option in self.am_settings.items():
            if option['type'] == 'divider': continue
            self.setting_values[option['qsid']] = self.am_config[key]
            self.saved_values[option['qsid']] = self.am_config[key]


    #MARK: Get Matrix
    #TODO: Also get mux_to_num for init keys, then just transfer the mux values to the keyboard, or send the indices and convert them on the kb?
    def get_transformation_matrices(self):
        rows = self.am_config['matrix_rows']
        cols = self.am_config['matrix_cols']
        size = rows * cols
        if size == 0: print("No analog matrix keyboard definition available!")

        data = b''
        for page in range(math.ceil(size / 32)):
            data += self.usb_send(self.dev, struct.pack("<BBH", AM_PREFIX, AM_GET_MATRIX_TO_NUM, page), retries=20)

        expected_size = math.ceil(size / 32) * 32
        if len(data) != expected_size: print("WARNING: The length of the transferred data doesn't match the expected length!")
        data = data[:size]
        
        col_str = '>' + ''.join(['B' for _ in range(cols)])
        self.matrix_to_num = [list(struct.unpack(col_str, data[row*cols:(row+1)*cols])) for row in range(rows)]

        self.num_to_matrix = [255 for _ in range(self.am_config['total_switch_num'])]
        for row in range(rows):
            for col in range(cols):
                idx = self.matrix_to_num[row][col]
                if idx != 255:
                    self.num_to_matrix[idx] = [row, col]
        for idx in self.num_to_matrix:
            if idx == 255: print("Warning: Corrupt matrix_to_num or num_to_matrix definition")


    #MARK: Get switch value
    def get_switch_value(self, index):
        data = self.usb_send(self.dev, struct.pack("<BBB", AM_PREFIX, AM_GET_SWITCH_VALUE, index), retries=20)

        if index == 255: return
        value = struct.unpack("<H", data[2:4])[0]
        #TODO: This might need to be adjusted for INVERT_ADC configs
        #TODO: Does this work correctly with deadzones etc
        if value == 0:
            self.switch_value = 0
        elif self.am_config['invert_adc']:
            self.switch_value = ((value - self.am_config['top_data'][index]) / (self.am_config['bottom_data'][index] - self.am_config['top_data'][index])) * 100
        else:
            self.switch_value = ((self.am_config['top_data'][index] - value) / (self.am_config['top_data'][index] - self.am_config['bottom_data'][index])) * 100


    def get_active_profile(self):
        data = self.usb_send(self.dev, struct.pack("BBB", AM_PREFIX, AM_GET_KEYBOARD_DEF, AM_GET_PROFILE), retries=20)
        self.profile = struct.unpack("B", data[2:3])[0]


    # Get the calibration data to accurately display the switch press height
    def get_calibration_data(self):
        size = self.am_config['total_switch_num'] * 2
        for idx, type in enumerate(['top_data', 'bottom_data']):
            data = b''
            for page in range(math.ceil(size/32)):
                data += self.usb_send(self.dev, struct.pack("BBBBB", AM_PREFIX, AM_GET_KEYBOARD_DEF, AM_GET_CALIBRATION_DATA, idx, page), retries=20)
            data = data[:size]
            unpack_str = '<' + ''.join(['H' for _ in range(self.am_config['total_switch_num'])])
            self.am_config[type] = struct.unpack(unpack_str, data)


    def set_active_profile(self, value):
        self.usb_send(self.dev, struct.pack("BBB", AM_PREFIX, AM_SET_ACTIVE_PROFILE, value), retries=20)


    #MARK: Set stuff
    def set_switch_height(self, index, profile, height_type, value):
        self.heights[height_type][profile][index] = value
        #TODO: Add timeout buffer before sending the value, as the slider sends updates every tick when dragged
        value = int(value * self.am_height_mult)
        height_idx = HEIGHT_TO_INDEX[height_type]
        self.usb_send(self.dev, struct.pack('<BBBBBH', AM_PREFIX, AM_SET_SWITCH_HEIGHT, index, profile, height_idx, value), retries=20)


    def set_switch_mode(self, index, profile, value):
        self.modes[profile][index] = value
        self.usb_send(self.dev, struct.pack('BBBBB', AM_PREFIX, AM_SET_SWITCH_MODE, index, profile, value), retries=20)


    def set_switch_priority(self, index, profile, value):
        self.priority_status[profile][index] = value
        value = 1 if value else 0
        self.usb_send(self.dev, struct.pack('BBBBB', AM_PREFIX, AM_SET_SWITCH_PRIORITY, index, profile, value), retries=20)

        # If a priority is given to a switch on a profile, mark it as a priority profile
        if value == 1 and self.am_config['priority_profiles'] & 1 << profile:
            self.toggle_priority_profiles(profile)


    # Even though the transaction expects 32 bits, the current implementation only supports up to 16 layers due to the split transaction only allowing 16 bit values
    def toggle_profile_layers(self, profile, layer):
        self.profile_layers[profile] ^= 1 << layer
        value = self.profile_layers[profile]
        self.usb_send(self.dev, struct.pack('<BBBI', AM_PREFIX, AM_SET_PROFILE_LAYERS, profile, value), retries=20)
        

    def set_profile_switch_mode(self, value):
        self.am_config['profile_switch_mode'] = value
        value |= self.am_config['default_profile'] << 4
        self.usb_send(self.dev, struct.pack('BBB', AM_PREFIX, AM_SET_PROFILE_CONFIG, value), retries=20)


    def set_default_profile(self, value):
        self.am_config['default_profile'] = value
        value = (value << 4) | self.am_config['default_profile']
        self.usb_send(self.dev, struct.pack('BBB', AM_PREFIX, AM_SET_PROFILE_CONFIG, value), retries=20)


    def toggle_priority_profiles(self, profile):
        self.am_config['priority_profiles'] ^= 1 << profile
        value = self.am_config['priority_profiles']
        index = 0
        self.usb_send(self.dev, struct.pack('<BBBH', AM_PREFIX, AM_SET_PRIORITY_CONFIG, index, value), retries=20)


    def set_priority_profiles(self, value):
        self.am_config['priority_profiles'] = value
        index = 0
        self.usb_send(self.dev, struct.pack('<BBBH', AM_PREFIX, AM_SET_PRIORITY_CONFIG, index, value), retries=20)


    def set_priority_level(self, value):
        self.am_config['priority_level'] = value
        index = 1
        self.usb_send(self.dev, struct.pack('BBBB', AM_PREFIX, AM_SET_PRIORITY_CONFIG, index, value), retries=20)


    def set_dynamic_calibration(self, type, value):
        self.am_config[type] = value
        index = DC_TO_INDEX[type]
        if type == 'dc_factor':
            value = int(value * MULT_MULT)
        self.usb_send(self.dev, struct.pack('BBBB', AM_PREFIX, AM_SET_DYNAMIC_CALIBRATION, index, value), retries=20)


    def set_deadzone(self, type, value):
        self.am_config[type] = value
        index = DEADZONE_TO_INDEX[type]
        if type in ['top_mult', 'right_mult', 'slave_mult']:
            value = int(value * MULT_MULT)
        self.usb_send(self.dev, struct.pack('BBBB', AM_PREFIX, AM_SET_DEADZONE, index, value), retries=20)


    def set_save_profile_lock(self, value):
        self.am_config['save_profile_lock'] = value
        value = 1 if value else 0
        self.usb_send(self.dev, struct.pack('BBB', AM_PREFIX, AM_SET_SAVE_PROFILE_LOCK, value), retries=20)


    # The value should be the actual amount, not the index of the highest profile
    def set_used_profiles(self, value):
        if value == 0:
            raise Warning("Invalid Profile amount: 0")
        self.am_config['used_profiles'] = value
        self.usb_send(self.dev, struct.pack('BBB', AM_PREFIX, AM_SET_USED_PROFILES, value), retries=20)
            
    def send_save_config(self):
        self.usb_send(self.dev, struct.pack('BB', AM_PREFIX, AM_SAVE_CONFIG), retries=20)

    def send_clear_calibration(self):
        self.usb_send(self.dev, struct.pack('BB', AM_PREFIX, AM_CLEAR_CALIBRATION_DATA), retries=20)

    def send_reset_data(self):
        self.usb_send(self.dev, struct.pack('BB', AM_PREFIX, AM_RESET_KEYBOARD_DATA), retries=20)

        #TODO: Reload the keyboard after clearing
        

    #MARK: Reload config
    def reload_analog_matrix(self):
        self.am_enabled = self.get_keyboard_def()
        self.index = 255

        if self.am_enabled:
            self.get_keyboard_data()
            self.get_transformation_matrices()
            self.get_calibration_data()


    #TODO: Implement this later
    #MARK: Save/restore
    # Returns the entire serialized analog matrix config as a list
    def save_analog_matrix(self):
        '''
        Things to save:
        All heights and modes
        The amount of used profiles
        Priority profiles and keys, also priority save status
        Profile layers and profile switch mode
        '''
        config = b''
        # for height_type in ['trigger_height', 'release_height', 'rt_press', 'rt_release']:
        #     config self.am_config
        return config


    # Converts the serialized list into the analog matrix config
    def restore_analog_matrix(self, data):
        pass

