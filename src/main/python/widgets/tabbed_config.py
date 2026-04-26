from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel, QPushButton, QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QProgressBar, QSlider, QLineEdit, QCheckBox
from util import tr
from protocol.analog_matrix import SWITCH_PRESS_HEIGHT, SWITCH_RELEASE_HEIGHT, SWITCH_PRESS_DISTANCE, SWITCH_RELEASE_DISTANCE

SLIDER_MULT = 50

class TabbedConfig(QScrollArea):
    def __init__(self):
        super().__init__()
        
        self.layout = QHBoxLayout()
        # self.layout.setContentsMargins(0, 0, 0, 0)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)

        self.keyboard = None

        self.setLayout(self.layout)

        self.mode = 255
        self.index = 255
        self.used_modes = []
        self.mode_selection = []

        self.tabbed_layouts = []

    #MARK: Rebuild
    def rebuild(self, keyboard):
        self.keyboard = keyboard

        # Delete old layouts
        for content in self.tabbed_layouts:
            if isinstance(content, ActuationWidget) or isinstance(content, SettingsWidget):
                content.destroy()
            content.deleteLater()
        self.tabbed_layouts = []

        if self.keyboard == None or not self.keyboard.am_enabled: return

        #TODO: Outsource these
        # Switch value bar
        self.switch_layout = QVBoxLayout()
        self.layout.addLayout(self.switch_layout)
        self.tabbed_layouts.append(self.switch_layout)
        switch_label = QLabel(tr("AnalogMatrixEditor", "Switch value"))
        self.switch_layout.addWidget(switch_label)
        self.tabbed_layouts.append(switch_label)
        self.switch_label = QLabel("No switch selected")
        self.switch_value_bar = QProgressBar(textVisible=False)
        self.switch_value_bar.setValue(100)
        self.switch_value_bar.setOrientation(Qt.Vertical)
        #TODO: When refreshing with a selected index, keyboard.switch_value isn't available even though it's initialized to 0 and am_config is printable
        # When refreshing the keyboards, the active key is deselected anyway -> clear the active index as well
        # if self.index < 255:
        #     self.keyboard.switch_value = 0
        #     matrix = self.keyboard.num_to_matrix[self.index]
        #     self.switch_label.setText(f"Current switch: {matrix}")
        #     self.switch_value_bar.setValue(100 - clamp_int(self.keyboard.switch_value))
        self.switch_layout.addWidget(self.switch_label)
        self.tabbed_layouts.append(self.switch_label)
        self.switch_value_bar.setRange(0, 100)
        self.switch_layout.addWidget(self.switch_value_bar)
        self.tabbed_layouts.append(self.switch_value_bar)

        # Key mode radio buttons
        self.key_mode_layout = QVBoxLayout()
        self.tabbed_layouts.append(self.key_mode_layout)
        key_mode_label = QLabel(tr("AnalogMatrixEditor", "Key mode"))
        self.key_mode_layout.addWidget(key_mode_label)
        self.tabbed_layouts.append(key_mode_label)
        mode_selection = []
        self.mode_group = QButtonGroup()
        for idx, mode in enumerate(("Trigger Height", "Rapid Trigger", "Continuous Rapid Trigger", "Constant Rapid Trigger")):
            #TODO: Need to add this back after debugging
            # if self.keyboard.am_config[f'use_{mode.lower().replace(" ", "_")}']:
                mode_selection.append((QRadioButton(mode), idx))
                self.key_mode_layout.addWidget(mode_selection[-1][0])
                self.mode_group.addButton(mode_selection[-1][0], idx)
                mode_selection[-1][0].toggled.connect(self.key_mode_changed)
                self.tabbed_layouts.append(mode_selection[-1][0])
                if self.index == 255:
                    mode_selection[-1][0].setDisabled(True)
                # Select the currently used mode
                elif self.keyboard.modes[self.keyboard.am_profile][self.index] == idx:
                    mode_selection[-1][0].setChecked(True)
        # Only add the key mode section if more than one mode is used
        if len(mode_selection) > 1:
            self.layout.addLayout(self.key_mode_layout)
        self.mode_selection = mode_selection
        self.tabbed_layouts.append(self.mode_group)
    
        # Actuation sliders/fields
        invert_sliders = False if self.keyboard.am_config['distance_from_bottom'] else True
        enable_sliders = False if self.index == 255 else True
        slider_range = (0, self.keyboard.am_config['travel_distance'] * SLIDER_MULT)
        # Trigger/Release height slider
        if self.keyboard.am_config['use_trigger_height']:
            self.move_heights_together = False
            self.height_field = ActuationWidget('Fixed Height', invert_sliders, slider_range, enable_sliders)
            self.layout.addLayout(self.height_field)
            self.height_field.press_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_PRESS_HEIGHT, value/SLIDER_MULT))
            self.height_field.release_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_RELEASE_HEIGHT, value/SLIDER_MULT))
            self.tabbed_layouts.append(self.height_field)
            self.height_field.checkbox.setEnabled(False)

        # Press/Release distance slider
        if self.keyboard.am_config['use_rt_distance']:
            self.move_distances_together = False
            self.rt_field = ActuationWidget('Rapid Trigger', invert_sliders, slider_range, enable_sliders)
            self.layout.addLayout(self.rt_field)
            self.rt_field.press_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_PRESS_DISTANCE, value/SLIDER_MULT))
            self.rt_field.release_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_RELEASE_DISTANCE, value/SLIDER_MULT))
            self.tabbed_layouts.append(self.rt_field)
            self.rt_field.checkbox.setEnabled(False)

        self.settings_layout = SettingsWidget(keyboard=keyboard, index=self.index, profile=self.keyboard.am_profile)
        self.layout.addLayout(self.settings_layout)
        self.tabbed_layouts.append(self.settings_layout)


    #MARK: Update
    def update_index(self, index):
        self.index = index
        
        if self.keyboard == None or not self.keyboard.am_enabled: return
        
        # Set the UI elements to the switch values
        if self.index < 255:
            matrix = self.keyboard.num_to_matrix[self.index]
            self.switch_label.setText(f"Current switch: {matrix}")
            self.keyboard.get_switch_value(index)
            self.switch_value_bar.setValue(100 - clamp_int(self.keyboard.switch_value))

            # Set the currently used mode
            mode = self.keyboard.modes[self.keyboard.am_profile][index]
            for idx, _ in enumerate(self.mode_selection):
                self.mode_selection[idx][0].setDisabled(False)
                if mode == self.mode_selection[idx][1]:
                    self.mode_selection[idx][0].setChecked(True)
                else:
                    self.mode_selection[idx][0].setChecked(False)
            
            if self.keyboard.am_config['use_trigger_height']:
                self.height_field.setEnabled(True)
                self.height_field.setValue('press', self.keyboard.heights['trigger_height'][self.keyboard.am_profile][self.index])
                self.height_field.setValue('release', self.keyboard.heights['release_height'][self.keyboard.am_profile][self.index])
                self.height_field.checkbox.setEnabled(True)

            if self.keyboard.am_config['use_rt_distance']:
                self.rt_field.setEnabled(True)
                self.rt_field.setValue('press', self.keyboard.heights['rt_press'][self.keyboard.am_profile][self.index])
                self.rt_field.setValue('release', self.keyboard.heights['rt_release'][self.keyboard.am_profile][self.index])
                self.rt_field.checkbox.setEnabled(True)

        # No switch is selected
        else:
            self.switch_label.setText("No switch selected")
            self.keyboard.get_switch_value(index)
            self.switch_value_bar.setValue(100)
            #TODO: Grey out all options while no switch is selected, but keep showing them

            for mode, _ in self.mode_selection:
                mode.setDisabled(True)

            if self.keyboard.am_config['use_trigger_height']:
                self.height_field.setEnabled(False)
                self.height_field.checkbox.setEnabled(False)

            if self.keyboard.am_config['use_rt_distance']:
                self.rt_field.setEnabled(False)
                self.rt_field.checkbox.setEnabled(False)

        self.settings_layout.update_index(keyboard=self.keyboard, index=self.index, profile=self.keyboard.am_profile)

        
    def key_mode_changed(self):
        mode = self.mode_group.checkedId()
        if self.index < 255 and mode != self.keyboard.modes[self.keyboard.am_profile][self.index]:
            self.keyboard.set_switch_mode(self.index, self.keyboard.am_profile, mode)


    def actuation_changed(self, index, value):
        if   index == SWITCH_PRESS_HEIGHT: 
            height_type = 'trigger_height'
            self.height_field.setValue('press', value)
            if self.move_heights_together:
                self.height_field.setValue('release', value)
                self.keyboard.set_switch_height(self.index, self.keyboard.am_profile, 'release', value)
            # Check if the trigger height has moved above the release height
            #TODO: Do the same the other way around
            elif self.keyboard.am_config['distance_from_bottom']:
                if value < float(self.height_field.release_entry.Text()):
                    self.height_field.setValue('release', value)
            else:
                if value > float(self.height_field.release_entry.Text()):
                    self.height_field.setValue('release', value)
        elif index == SWITCH_RELEASE_HEIGHT:
            height_type = 'release_height'
            self.height_field.setValue('release', value)

        #TODO: How does this function work? If sync is active, does it already get the synced value on both calls? Probably, meaning I could simplify rt sync stuff
        elif index == SWITCH_PRESS_DISTANCE:
            height_type = 'rt_press'
            self.rt_field.setValue('press', value)
            if self.rt_field.sync:
                self.rt_field.setValue('release', value + self.rt_field.offset)

        elif index == SWITCH_RELEASE_DISTANCE:
            height_type = 'rt_release'
            # Since setValue is already handled by the press part when synced, we don't need to set it again
            if not self.rt_field.sync:
                self.rt_field.setValue('release', value)

        self.keyboard.set_switch_height(self.index, self.keyboard.am_profile, height_type, value)


# From squishyliquid
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.orientation() == Qt.Horizontal:
                # Subtract half the handle width (6 px)
                pos = event.x() - 6
                ratio = pos / (self.width() - 12)
            else:  # vertical
                # Subtract half the handle height (6 px)
                pos = event.y() - 6
                ratio = pos / (self.height() - 12)

            ratio = max(0, min(1, ratio))

            # Adjust ratio based on inverted appearance
            if self.invertedAppearance() != (self.orientation() == Qt.Vertical):
                ratio = 1 - ratio

            value = round(self.minimum() + ratio * (self.maximum() - self.minimum()))
            self.setValue(value)
            event.accept()
        super().mousePressEvent(event)


#MARK: Classes
class ActuationSlider(ClickableSlider):
    def __init__(self, invert=True, range=(0, 100), enabled=True):
        super().__init__()
        self.setInvertedAppearance(invert)
        self.setRange(range[0], range[1])
        self.setEnabled(enabled)


class BetterLineEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Timer needed, because selectAll is triggered before the mouse click is processed otherwise
        QTimer.singleShot(0, self.selectAll)


#MARK: Actuation
class ActuationWidget(QVBoxLayout):
    def __init__(self, label, invert=True, slider_range=(0, 100), enabled=True, switch_travel=4.0):
        super().__init__()
        self.contents = []
        self.switch_travel = switch_travel
        self.offset = 0.0
        self.sync = False
        self.label = label
        actuation_label = QLabel(tr("AnalogMatrixEditor", label))
        self.addWidget(actuation_label)

        self.press_layout = QHBoxLayout()
        self.addLayout(self.press_layout)
        self.press_slider = ActuationSlider(invert, slider_range, enabled)
        self.press_layout.addWidget(self.press_slider)
        entry_layout = QVBoxLayout()
        press_label = QLabel(tr("AnalogMatrixEditor", "Press"))
        entry_layout.addWidget(press_label)
        self.press_entry = BetterLineEdit()
        self.press_entry.editingFinished.connect(lambda: self.processText('press', self.press_entry.displayText()))
        self.press_entry.setMaxLength(4)
        entry_layout.addWidget(self.press_entry)
        self.press_entry.setReadOnly(not enabled)
        self.press_layout.addLayout(entry_layout)

        self.release_layout = QHBoxLayout()
        self.addLayout(self.release_layout)
        self.release_slider = ActuationSlider(invert, slider_range, enabled)
        self.release_layout.addWidget(self.release_slider)
        entry_layout = QVBoxLayout()
        release_label = QLabel(tr("AnalogMatrixEditor", "Release"))
        entry_layout.addWidget(release_label)
        self.release_entry = BetterLineEdit()
        self.release_entry.editingFinished.connect(lambda: self.processText('release', self.release_entry.displayText()))
        self.release_entry.setMaxLength(4)
        entry_layout.addWidget(self.release_entry)
        self.release_entry.setReadOnly(not enabled)
        self.release_layout.addLayout(entry_layout)

        self.checkbox = QCheckBox('Sync values')
        self.checkbox.stateChanged.connect(self.toggleSync)
        self.addWidget(self.checkbox)
        self.contents.append(self.checkbox)
        offset_label = QLabel(tr("AnalogMatrixEditor", "Offset"))
        self.offset_entry = BetterLineEdit()
        self.offset_entry.setText('0.00')
        self.offset_entry.editingFinished.connect(lambda: self.processText('offset', self.offset_entry.displayText()))
        self.offset_entry.setMaxLength(4)
        self.offset_entry.setReadOnly(not enabled)
        self.offset_entry.setEnabled(enabled)
        self.addWidget(offset_label)
        self.addWidget(self.offset_entry)

        self.contents += [actuation_label, self.press_slider, self.press_entry, self.release_slider, self.release_entry, entry_layout, press_label, self.press_layout, release_label, self.release_layout, self.checkbox, offset_label, self.offset_entry]


    def setEnabled(self, state=None):
        # If the slider states are synced, don't allow moving the release sliders
        if state != None:
            self.press_entry.setReadOnly(not state)
            self.press_entry.setEnabled(state)
            self.press_slider.setEnabled(state)
            self.offset_entry.setEnabled(state)
            self.offset_entry.setReadOnly(not state)

        else: state = True
        self.release_entry.setReadOnly(self.sync or not state)
        self.release_entry.setDisabled(self.sync or not state)
        self.release_slider.setDisabled(self.sync or not state)
        

    def processText(self, height_type, value):
        try:
            if height_type == 'offset':
                # Negative offsets are allowed for rapid trigger
                if self.label == 'Rapid Trigger':
                    value = clamp(float(value), -self.switch_travel, self.switch_travel) * 100
                else:
                    value = clamp(float(value), 0, self.switch_travel) * 100

                # Round down to the closest slider step
                self.offset = (value - (value % 2)) / 100
                self.offset_entry.setText(str(self.offset))
            else:
                value = clamp(float(value), largest=self.switch_travel) * 100
                value -= value % 2
                self.setValue(height_type, value / 100)
        except:
            print(f"Failed processing {height_type}")
            #TODO: Add proper error message here


    def setValue(self, height_type, value):
        value = clamp(value, largest=self.switch_travel)
        if height_type == 'press':
            self.press_slider.setValue(int(value * SLIDER_MULT))
            self.press_entry.setText(str(value))
        elif height_type == 'release':
            self.release_slider.setValue(int(value * SLIDER_MULT))
            self.release_entry.setText(str(value))


    def toggleSync(self):
        self.sync = not self.sync
        self.setEnabled()


    def destroy(self):
        for content in self.contents:
            content.deleteLater()
        self.contents = []

# Contains the rest of the per switch settings
# When init is called, we already have the keyboard data available
#MARK: Settings
class SettingsWidget(QVBoxLayout):
    def __init__(self, keyboard=None, index=255, profile=0):
        super().__init__()
        self.keyboard = keyboard
        self.use_priority = keyboard.am_config['priority_mode']
        self.index = index
        self.priority = False
        if index < 255:
            if keyboard.am_config['use_trigger_height']:
                self.press_height = keyboard.heights['trigger_height'][profile][index]
                self.release_height = keyboard.heights['release_height'][profile][index]
            if keyboard.am_config['use_rt_distance']:
                self.rt_press = keyboard.heights['rt_press'][profile][index]
                self.rt_release = keyboard.heights['rt_release'][profile][index]
            self.mode = keyboard.modes[profile][index]
            if self.use_priority:
                self.priority = keyboard.priority_status[profile][index]
        self.contents = []

        label = QLabel(tr("AnalogMatrixEditor", "Switch settings"))
        self.addWidget(label)
        self.contents.append(label)

        if self.use_priority:
            self.priority_checkbox = QCheckBox('Priority')
            self.addWidget(self.priority_checkbox)
            self.priority_checkbox.stateChanged.connect(self.togglePriority)
            self.contents.append(self.priority_checkbox)
            if index < 255:
                self.priority_checkbox.setChecked(self.keyboard.priority_status[profile][index])
            else:
                self.priority_checkbox.setEnabled(False)

        self.previous_button = QPushButton('Reset to Previous')
        self.addWidget(self.previous_button)
        self.previous_button.clicked.connect(self.reset_to_previous)
        self.previous_button.setDisabled(index==255)
        self.contents.append(self.previous_button)

        self.default_button = QPushButton('Reset to Defaults')
        self.addWidget(self.default_button)
        self.default_button.clicked.connect(self.reset_to_default)
        self.default_button.setDisabled(index==255)
        self.contents.append(self.default_button)

        self.save_button = QPushButton('Save configuration')
        self.addWidget(self.save_button)
        self.save_button.clicked.connect(self.keyboard.send_save_config)
        self.contents.append(self.save_button)

    def update_index(self, keyboard, index, profile):
        self.keyboard = keyboard
        self.index = index
        self.profile = profile
        if index < 255:
            if self.keyboard.am_config['use_trigger_height']:
                self.press_height = self.keyboard.heights['trigger_height'][profile][index]
                self.release_height = self.keyboard.heights['release_height'][profile][index]
            if self.keyboard.am_config['use_rt_distance']:
                self.rt_press = self.keyboard.heights['rt_press'][profile][index]
                self.rt_release = self.keyboard.heights['rt_release'][profile][index]
            self.mode = self.keyboard.modes[profile][index]
            self.prev_priority = self.keyboard.priority_status[profile][index]

            self.previous_button.setEnabled(True)
            self.default_button.setEnabled(True)
            if self.use_priority:
                self.priority_checkbox.setChecked(self.keyboard.priority_status[profile][index])
                self.priority_checkbox.setEnabled(True)
        else:
            self.previous_button.setEnabled(False)
            self.default_button.setEnabled(False)
            if self.use_priority:
                self.priority_checkbox.setEnabled(False)


    def togglePriority(self):
        self.priority = not self.priority
        self.keyboard.set_switch_priority(self.index, self.profile, self.priority)


    # Reset the switch to the state it was in before
    #TODO: Add a set_switch_profile function that adjusts the config in the GUI in bulk, then calls the HID transactions for the new config
    def reset_to_previous(self):
        print("Previous!")
        pass

    # Reset the switch to the default state
    def reset_to_default(self):
        print("Default!")
        pass
    
    def destroy(self):
        for content in self.contents:
            content.deleteLater()
        self.contents = []



            
def clamp(n, smallest=0.0, largest=100.0): return max(smallest, min(n, largest))

def clamp_int(n, smallest=0, largest=100): return max(smallest, min(n, largest))