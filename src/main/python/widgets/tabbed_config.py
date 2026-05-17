from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QLabel, QPushButton, QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QProgressBar, QSlider, QLineEdit, QCheckBox, QComboBox
from PyQt5.QtGui import QPalette
from util import tr
from protocol.analog_matrix import SWITCH_PRESS_HEIGHT, SWITCH_RELEASE_HEIGHT, SWITCH_PRESS_DISTANCE, SWITCH_RELEASE_DISTANCE

SLIDER_MULT = 50

class TabbedConfig(QScrollArea):
    def __init__(self):
        super().__init__()
        
        self.setMinimumHeight(330)
        self.layout = QHBoxLayout()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)

        #TODO: To use style sheets here, I'd need to wrap each segment into a helper layout + widget and apply the style to that widget
        # self.switch_helper = QWidget()
        # self.switch_helper.setStyleSheet("background-color: {}".format(QApplication.palette().color(QPalette.Button).lighter(130).name()))
        # self.layout.addWidget(self.switch_helper)

        self.keyboard = None

        self.setLayout(self.layout)

        self.mode = 255
        self.index = 255
        self.index_list = []
        self.used_modes = []
        self.mode_selection = []

        self.tabbed_layouts = []

    #MARK: Rebuild
    def rebuild(self, keyboard):
        self.keyboard = keyboard

        # Delete old layouts
        for content in self.tabbed_layouts:
            if isinstance(content, ActuationWidget) or isinstance(content, SwitchSettingsWidget):
                content.destroy()
            content.deleteLater()
        self.tabbed_layouts = []

        if self.keyboard == None or not self.keyboard.am_enabled: return

        # Switch value bar
        self.switch_layout = QVBoxLayout()
        self.switch_layout.setAlignment(Qt.AlignCenter)
        self.switch_layout.setContentsMargins(10, 0, 10, 0)
        #NOTE: To use style sheets here, I'd need to wrap each segment into a helper layout + widget and apply the style to that widget
        # self.switch_helper.setLayout(self.switch_layout)
        self.layout.addLayout(self.switch_layout)
        self.tabbed_layouts.append(self.switch_layout)
        switch_label = QLabel(tr("AnalogMatrixEditor", "Switch value"))
        self.switch_layout.addWidget(switch_label)
        self.tabbed_layouts.append(switch_label)
        self.switch_label = QLabel(tr("AnalogMatrixEditor", "No switch selected"))
        self.switch_label.setMinimumWidth(140) # Keeps the label from expanding when a switch is selected
        #TODO: Stop the animation from playing (style guide?)
        self.switch_value_bar = QProgressBar(textVisible=False)
        self.switch_value_bar.setOrientation(Qt.Vertical)
        self.switch_value_bar.setInvertedAppearance(True)
        self.switch_value_bar.setRange(0, 100)
        #TODO: When refreshing with a selected index, keyboard.switch_value isn't available even though it's initialized to 0 and am_config is printable
        # When refreshing the keyboards, the active key is deselected anyway -> clear the active index as well
        # if self.index < 255:
        #     self.keyboard.switch_value = 0
        #     matrix = self.keyboard.num_to_matrix[self.index]
        #     self.switch_label.setText(f"Current switch: {matrix}")
        #     self.switch_value_bar.setValue(100 - clamp_int(self.keyboard.switch_value))
        self.switch_layout.addWidget(self.switch_label)
        self.tabbed_layouts.append(self.switch_label)
        self.switch_layout.addWidget(self.switch_value_bar)
        self.tabbed_layouts.append(self.switch_value_bar)

        # Key mode radio buttons
        self.key_mode_layout = QVBoxLayout()
        self.key_mode_layout.setAlignment(Qt.AlignCenter)
        self.key_mode_layout.setContentsMargins(10, 0, 10, 0)
        self.tabbed_layouts.append(self.key_mode_layout)
        key_mode_label = QLabel(tr("AnalogMatrixEditor", "Key mode"))
        key_mode_label.setAlignment(Qt.AlignBottom)
        self.key_mode_layout.addWidget(key_mode_label)
        self.tabbed_layouts.append(key_mode_label)
        mode_selection = []
        self.mode_group = QButtonGroup()
        for idx, mode in enumerate(("Trigger Height", "Rapid Trigger", "Continuous Rapid Trigger", "Constant Rapid Trigger")):
            mode_selection.append((QRadioButton(mode), idx))
            self.key_mode_layout.addWidget(mode_selection[-1][0])
            self.mode_group.addButton(mode_selection[-1][0], idx)
            mode_selection[-1][0].toggled.connect(self.key_mode_changed)
            self.tabbed_layouts.append(mode_selection[-1][0])
            if self.index == 255 or self.keyboard.am_config[f'use_{mode.lower().replace(" ", "_")}']:
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
        enable_sliders = self.index != 255
        invert_sliders = not self.keyboard.am_config['distance_from_bottom']
        slider_range = (0, self.keyboard.am_config['travel_distance'] * SLIDER_MULT)
        # Trigger/Release height slider
        self.height_field = ActuationWidget('Fixed Height', invert_sliders, slider_range, enable_sliders, keyboard.am_config['travel_distance'], keyboard.am_config['use_high_resolution'])
        self.layout.addLayout(self.height_field)
        self.height_field.press_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_PRESS_HEIGHT, value/SLIDER_MULT))
        self.height_field.release_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_RELEASE_HEIGHT, value/SLIDER_MULT))
        self.tabbed_layouts.append(self.height_field)
        self.height_field.setEnabled(False)

        # Press/Release distance slider
        self.rt_field = ActuationWidget('Rapid Trigger', invert_sliders, slider_range, enable_sliders, keyboard.am_config['travel_distance'], keyboard.am_config['use_high_resolution'])
        self.layout.addLayout(self.rt_field)
        self.rt_field.press_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_PRESS_DISTANCE, value/SLIDER_MULT))
        self.rt_field.release_slider.valueChanged.connect(lambda value: self.actuation_changed(SWITCH_RELEASE_DISTANCE, value/SLIDER_MULT))
        self.tabbed_layouts.append(self.rt_field)
        self.rt_field.setEnabled(False)

        self.settings_layout = SwitchSettingsWidget(keyboard=keyboard, index=self.index, profile=self.keyboard.am_profile)
        self.settings_layout.setContentsMargins(10, 0, 10, 0)
        self.settings_layout.resetPrevious.connect(self._update_values)
        self.settings_layout.resetDefault.connect(self._update_values)
        self.layout.addLayout(self.settings_layout)
        self.tabbed_layouts.append(self.settings_layout)

    # Helper function to update the displayed values
    def _update_values(self):
        self.update_index(self.index, self.index_list)


    #MARK: Update
    def update_index(self, index, index_list=[]):
        self.index = index
        self.index_list = index_list
        
        if self.keyboard == None or not self.keyboard.am_enabled: return
        
        # Set the UI elements to the switch values
        if self.index < 255:
            matrix = self.keyboard.num_to_matrix[self.index]
            self.switch_label.setText(f"Current switch: {matrix}")
            self.keyboard.get_switch_value(index)
            self.switch_value_bar.setValue(clamp_int(self.keyboard.switch_value))

            # Set the currently used mode
            used_mode = self.keyboard.modes[self.keyboard.am_profile][index]
            for idx, mode in enumerate(("Trigger Height", "Rapid Trigger", "Continuous Rapid Trigger", "Constant Rapid Trigger")):
                if self.keyboard.am_config[f'use_{mode.lower().replace(" ", "_")}']:
                    self.mode_selection[idx][0].setDisabled(False)
                    if used_mode == self.mode_selection[idx][1]:
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
            self.switch_value_bar.setValue(0)
            #TODO: Grey out all options while no switch is selected, but keep showing them

            for mode, _ in self.mode_selection:
                mode.setDisabled(True)

            if self.keyboard.am_config['use_trigger_height']:
                self.height_field.setEnabled(False)
                self.height_field.checkbox.setEnabled(False)

            if self.keyboard.am_config['use_rt_distance']:
                self.rt_field.setEnabled(False)
                self.rt_field.checkbox.setEnabled(False)

        self.settings_layout.update_index(keyboard=self.keyboard, index=self.index, index_list=self.index_list, profile=self.keyboard.am_profile)


    def key_mode_changed(self):
        mode = self.mode_group.checkedId()
        for index in self.index_list:
            if mode != self.keyboard.modes[self.keyboard.am_profile][index]:
                self.keyboard.set_switch_mode(index, self.keyboard.am_profile, mode)


    #TODO: This is called anytime the text in the fields changes
    #       -> Hence why having sync enabled applies it to any switch that's selected after
    #       -> Also why selecting multiple switches applies the settings of one to all of them
    #       -> The current issue where text isn't grabbed is also because of this, caused by switching from an empty release field to a full one
    #       -> Since it should only be called if a value is changed, and not when a new switch is selected, check for an index change
    #           -> Need to make sure that the text is still updated correctly though, try to decouple text changes from actual setting changes if possible
    def actuation_changed(self, actuation_index, value):
        if   actuation_index == SWITCH_PRESS_HEIGHT: 
            height_type = 'trigger_height'
            self.height_field.setValue('press', value)
            if self.height_field.sync:
                self.height_field.setValue('release', value + self.height_field.offset)
            # Check if the trigger height has moved above the release height
            elif self.keyboard.am_config['distance_from_bottom']:
                text = self.height_field.release_entry.text()
                if text is not '' and value > float(text):
                    self.height_field.setValue('release', value)
            else:
                #TODO: This is delayed by one, is that a problem?
                text = self.height_field.release_entry.text()
                if text is not '' and value < float(text):
                    self.height_field.setValue('release', value)
                    
        elif actuation_index == SWITCH_RELEASE_HEIGHT:
            height_type = 'release_height'
            if not self.height_field.sync:
                self.height_field.setValue('release', value)
                # Check if the release height has moved below the press height
                if self.keyboard.am_config['distance_from_bottom']:
                    if value < float(self.height_field.press_entry.text()):
                        self.height_field.setValue('press', value)
                else:
                    if value > float(self.height_field.press_entry.text()):
                        self.height_field.setValue('press', value)

        elif actuation_index == SWITCH_PRESS_DISTANCE:
            height_type = 'rt_press'
            self.rt_field.setValue('press', value)
            if self.rt_field.sync:
                self.rt_field.setValue('release', value + self.rt_field.offset)

        elif actuation_index == SWITCH_RELEASE_DISTANCE:
            height_type = 'rt_release'
            # Since setValue is already handled by the press part when synced, we don't need to set it again
            if not self.rt_field.sync:
                self.rt_field.setValue('release', value)

        #TODO: Is it perhaps calling actuation changed recursively many times, when heights are synced?
        for index in self.index_list:
            self.keyboard.set_switch_height(index, self.keyboard.am_profile, height_type, value)


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
        self.setInvertedControls(invert)
        self.setRange(range[0], range[1])
        self.setEnabled(enabled)


class BetterLineEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Timer needed, because selectAll is triggered before the mouse click is processed otherwise
        QTimer.singleShot(0, self.selectAll)


#MARK: Actuation
class ActuationWidget(QVBoxLayout):
    def __init__(self, label, invert=True, slider_range=(0, 100), enabled=True, switch_travel=4.0, high_resolution=False):
        super().__init__()
        self.contents = []
        self.switch_travel = switch_travel
        self.offset = 0.0
        self.sync = False
        self.label = label
        self.high_resolution = high_resolution
        self.setContentsMargins(10, 0, 10, 0)
        actuation_label = QLabel(tr("AnalogMatrixEditor", label))
        self.addWidget(actuation_label)

        self.press_layout = QHBoxLayout()
        self.addLayout(self.press_layout)
        self.press_slider = ActuationSlider(invert, slider_range, enabled)
        self.press_layout.addWidget(self.press_slider)
        entry_layout = QVBoxLayout()
        self.buttons = []
        for val in [0.5, 0.1, 0.01, -0.5, -0.1, -0.01] if high_resolution else [0.5, 0.1, 0.02, -0.5, -0.1, -0.02]:
            button = QPushButton(str(val))
            button.clicked.connect(lambda _, t='press', v=val: self.incrementValue(t, v))
            button.setEnabled(False)
            self.buttons.append(button)
        plus_buttons = QHBoxLayout()
        for button in self.buttons[:3]:
            plus_buttons.addWidget(button)
        entry_layout.addLayout(plus_buttons)
        press_label = QLabel(tr("AnalogMatrixEditor", "Press"))
        entry_layout.addWidget(press_label)
        minus_buttons = QHBoxLayout()
        for button in self.buttons[3:]:
            minus_buttons.addWidget(button)
        entry_layout.addLayout(minus_buttons)
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
        for val in [0.5, 0.1, 0.01, -0.5, -0.1, -0.01] if high_resolution else [0.5, 0.1, 0.02, -0.5, -0.1, -0.02]:
            button = QPushButton(str(val))
            button.clicked.connect(lambda _, t='release', v=val: self.incrementValue(t, v))
            button.setEnabled(False)
            self.buttons.append(button)
        plus_buttons = QHBoxLayout()
        for button in self.buttons[6:9]:
            plus_buttons.addWidget(button)
        entry_layout.addLayout(plus_buttons)
        release_label = QLabel(tr("AnalogMatrixEditor", "Release"))
        entry_layout.addWidget(release_label)
        minus_buttons = QHBoxLayout()
        for button in self.buttons[9:]:
            minus_buttons.addWidget(button)
        entry_layout.addLayout(minus_buttons)
        self.release_entry = BetterLineEdit()
        self.release_entry.editingFinished.connect(lambda: self.processText('release', self.release_entry.displayText()))
        self.release_entry.setMaxLength(4)
        entry_layout.addWidget(self.release_entry)
        self.release_entry.setReadOnly(not enabled)
        self.release_layout.addLayout(entry_layout)

        self.checkbox = QCheckBox('Sync values')
        self.checkbox.stateChanged.connect(self.toggleSync)
        self.addWidget(self.checkbox)
        offset_label = QLabel(tr("AnalogMatrixEditor", "Offset"))
        self.offset_entry = BetterLineEdit()
        self.offset_entry.setText('0.00')
        self.offset_entry.editingFinished.connect(lambda: self.processText('offset', self.offset_entry.displayText()))
        self.offset_entry.setMaxLength(4)
        self.offset_entry.setReadOnly(not enabled)
        self.offset_entry.setEnabled(enabled)
        self.addWidget(offset_label)
        self.addWidget(self.offset_entry)

        self.contents += [actuation_label, self.press_slider, self.press_entry, self.release_slider, self.release_entry, entry_layout, press_label, self.press_layout, release_label, self.release_layout, self.checkbox, offset_label, self.offset_entry, plus_buttons, minus_buttons, self.checkbox] + self.buttons


    def incrementValue(self, height_type, amount):
        if height_type == 'press':
            value = float(self.press_entry.text()) + amount
        elif height_type == 'release':
            value = float(self.release_entry.text()) + amount

        self.setValue(height_type, value)


    def setEnabled(self, state=None):
        if state != None:
            self.press_entry.setReadOnly(not state)
            self.press_entry.setEnabled(state)
            self.press_slider.setEnabled(state)
            self.offset_entry.setEnabled(state)
            self.offset_entry.setReadOnly(not state)
            for button in self.buttons[:6]:
                button.setEnabled(state)

        # If the slider states are synced, don't allow moving the release sliders
        else: state = True
        self.release_entry.setReadOnly(self.sync or not state)
        self.release_entry.setDisabled(self.sync or not state)
        self.release_slider.setDisabled(self.sync or not state)
        for button in self.buttons[6:]:
            button.setDisabled(self.sync or not state)
        

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

                # If sync is enabled, immediately apply the offset
                if self.sync:
                    release_value = clamp(float(self.press_entry.text()) + self.offset, 0, self.switch_travel)
                    self.setValue('release', release_value)

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
        # If sync is enabled, immediately apply the offset
        if self.sync:
            release_value = clamp(float(self.press_entry.text()) + self.offset, 0, self.switch_travel)
            self.setValue('release', release_value)
        self.setEnabled()


    def destroy(self):
        for content in self.contents:
            content.deleteLater()
        self.contents = []


# Contains the rest of the per switch settings
# When init is called, we already have the keyboard data available
#MARK: Settings
class SwitchSettingsWidget(QVBoxLayout):
    resetPrevious = pyqtSignal()
    resetDefault = pyqtSignal()

    def __init__(self, keyboard=None, index=255, profile=0):
        super().__init__()
        self.keyboard = keyboard
        self.config = []
        self.index = index
        self.index_list = []
        self.profile = profile
        self.contents = []
        self.init_modes = ['None']

        self.setAlignment(Qt.AlignCenter)
        label = QLabel(tr("AnalogMatrixEditor", "Switch settings"))
        self.addWidget(label)
        self.contents.append(label)
        self.priority_checkbox = QCheckBox('Priority')
        self.addWidget(self.priority_checkbox)
        self.priority_checkbox.stateChanged.connect(self.togglePriority)
        self.contents.append(self.priority_checkbox)
        if keyboard.am_config['priority_indices']:
            self.priority_checkbox.setEnabled(True)

        combo_label = QLabel(tr("AnalogMatrixEditor", "Init key mode"))
        self.init_combo = QComboBox()
        self.init_combo.currentIndexChanged.connect(self.setInitKey)
        self.init_combo.setEnabled(len(self.index_list) == 1)
        self.init_combo.addItem('None')
        self.addWidget(combo_label)
        self.addWidget(self.init_combo)

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

        self.contents += [combo_label, self.init_combo]

    def update_index(self, keyboard, index, index_list, profile):
        self.keyboard = keyboard
        self.index = index
        self.index_list = index_list
        self.profile = profile
        if index < 255:
            self.config = []
            if keyboard.am_config['priority_indices']:
                self.priority_checkbox.setEnabled(True)
                
            for idx, index in enumerate(index_list):
                self.config.append({})
                if self.keyboard.am_config['use_trigger_height']:
                    self.config[idx]['trigger_height'] = self.keyboard.heights['trigger_height'][profile][index]
                    self.config[idx]['release_height'] = self.keyboard.heights['release_height'][profile][index]
                if self.keyboard.am_config['use_rt_distance']:
                    self.config[idx]['rt_press'] = self.keyboard.heights['rt_press'][profile][index]
                    self.config[idx]['rt_release'] = self.keyboard.heights['rt_release'][profile][index]
                self.config[idx]['mode'] = self.keyboard.modes[profile][index]
                self.config[idx]['priority_status'] = self.keyboard.priority_status[profile][index]

                self.previous_button.setEnabled(True)
                self.default_button.setEnabled(True)
                if self.config[idx]['priority_status']:
                    self.priority_checkbox.setChecked(self.config[idx]['priority_status'])

            #TODO: 
            if len(self.index_list) == 1:
                self.init_combo.setEnabled(True)
                self.init_combo.clear()
                self.init_combo.addItems

        else:
            self.previous_button.setEnabled(False)
            self.default_button.setEnabled(False)
            self.priority_checkbox.setEnabled(False)

    
    def setInitKey(self):
        pass


    def togglePriority(self):
        #TODO: Check that the correct state is grabbed
        if self.config == []: return
        status = not self.config[-1]['priority_status']
        self.config[-1]['priority_status'] = status
        for idx, index in enumerate(self.index_list):
            self.keyboard.set_switch_priority(index, self.profile, self.config[idx]['priority_status'])


    # Reset the switch to the state it was in before being selected
    def reset_to_previous(self):
        profile = self.profile
        for idx, index in enumerate(self.index_list):
            if self.keyboard.am_config['use_trigger_height']:
                if self.config[idx]['trigger_height'] != self.keyboard.heights['trigger_height'][profile][index]:
                    self.keyboard.set_switch_height(index, profile, 'trigger_height', self.config[idx]['trigger_height'])
                if self.config[idx]['release_height'] != self.keyboard.heights['release_height'][profile][index]:
                    self.keyboard.set_switch_height(index, profile, 'release_height', self.config[idx]['release_height'])
            if self.keyboard.am_config['use_rt_distance']:
                if self.config[idx]['rt_press'] != self.keyboard.heights['rt_press'][profile][index]:
                    self.keyboard.set_switch_height(index, profile, 'rt_press', self.config[idx]['rt_press'])
                if self.config[idx]['rt_release'] != self.keyboard.heights['rt_release'][profile][index]:
                    self.keyboard.set_switch_height(index, profile, 'rt_release', self.config[idx]['rt_release'])

            if self.config[idx]['mode'] != self.keyboard.modes[profile][index]:
                self.keyboard.set_switch_mode(index, profile, self.config[idx]['mode'])
                
            if self.config[idx]['priority_status'] != self.keyboard.priority_status[profile][index]:
                self.keyboard.set_switch_priority(index, profile, self.config[idx]['priority_status'])

        self.resetPrevious.emit()


    # Reset the switch to the default state
    def reset_to_default(self):
        profile = self.profile
        PRESS_HEIGHT = 1.5 if not self.keyboard.am_config['distance_from_bottom'] else self.keyboard.am_config['travel_distance'] - 1.5
        RELEASE_HEIGHT = 1.3 if not self.keyboard.am_config['distance_from_bottom'] else self.keyboard.am_config['travel_distance'] - 1.3
        RT_DISTANCE = 0.5
        MODE = 0
        for index in self.index_list:
            if self.keyboard.am_config['use_trigger_height']:
                if self.keyboard.heights['trigger_height'][profile][index] != PRESS_HEIGHT:
                    self.keyboard.set_switch_height(index, profile, 'trigger_height', PRESS_HEIGHT)
                if self.keyboard.heights['release_height'][profile][index] != RELEASE_HEIGHT:
                    self.keyboard.set_switch_height(index, profile, 'release_height', RELEASE_HEIGHT)
            if self.keyboard.am_config['use_rt_distance']:
                if self.keyboard.heights['rt_press'][profile][index] != RT_DISTANCE:
                    self.keyboard.set_switch_height(index, profile, 'rt_press', RT_DISTANCE)
                if self.keyboard.heights['rt_release'][profile][index] != RT_DISTANCE:
                    self.keyboard.set_switch_height(index, profile, 'rt_release', RT_DISTANCE)

            if self.keyboard.modes[profile][index] != MODE:
                self.keyboard.set_switch_mode(index, profile, MODE)
                
            if self.keyboard.priority_status[profile][index] != False:
                self.keyboard.set_switch_priority(index, profile, False)

        self.resetDefault.emit()
    
    def destroy(self):
        for content in self.contents:
            content.deleteLater()
        self.contents = []



            
def clamp(n, smallest=0.0, largest=100.0): return max(smallest, min(n, largest))

def clamp_int(n, smallest=0, largest=100): return max(smallest, min(n, largest))