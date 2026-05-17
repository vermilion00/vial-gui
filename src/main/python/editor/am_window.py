# SPDX-License-Identifier: GPL-2.0-or-later
import json
from collections import defaultdict

from PyQt5.QtCore import Qt, QSize, QRect, QPointF, pyqtSignal, QEvent, QRectF, QPoint, QLine
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QTransform, QBrush, QPolygonF, QPalette
from PyQt5.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QMessageBox, QWidget, QSpinBox, QDoubleSpinBox, QComboBox, QToolTip, QApplication, QRubberBand, QAction, QSizePolicy, QScrollArea, QPushButton
from themes import Theme

from editor.basic_editor import BasicEditor
from editor.qmk_settings import BooleanOption, IntegerOption, GenericOption
from widgets.keyboard_widget import KeyboardWidget
from widgets.square_button import SquareButton
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard
from protocol.analog_matrix import ProtocolAnalogMatrix, SWITCH_PRESS_HEIGHT, SWITCH_RELEASE_HEIGHT, SWITCH_PRESS_DISTANCE, SWITCH_RELEASE_DISTANCE, SWITCH_MODE, SWITCH_PRIORITY
from widgets.tabbed_config import TabbedConfig

BOX_SELECTION = 0
PATH_SELECTION = 1
INCLUSIVE_MODE = 0
EXCLUSIVE_MODE = 1

class ClickableWidget(QWidget):

    clicked = pyqtSignal()
    # resized = pyqtSignal()

    def mousePressEvent(self, evt):
        super().mousePressEvent(evt)
        self.clicked.emit()

    # def resizeEvent(self, ev):
    #     self.resized.emit()


class AnalogMatrixEditor(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()

        self.keyboard = None

        self.layout_editor = layout_editor

        self.layout_profiles = QHBoxLayout()
        self.layout_size = QVBoxLayout()
        self.layout_layers = QHBoxLayout()
        profile_label = QLabel(tr("AnalogMatrixEditor", "Profile"))
        layer_label = QLabel(tr("AnalogMatrixEditor", "Layers"))

        layout_labels_container = QHBoxLayout()
        layout_labels_container.addWidget(profile_label)
        layout_labels_container.addLayout(self.layout_profiles)
        layout_labels_container.addStretch()
        layout_labels_container.addWidget(layer_label)
        layout_labels_container.addLayout(self.layout_layers)
        layout_labels_container.addLayout(self.layout_size)

        self.container = AMKeyboardWidget(layout_editor, self.keyboard)
        self.container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.container.clicked.connect(self.on_key_clicked)
        self.container.deselected.connect(self.on_key_deselected)

        layout = QVBoxLayout()
        layout.addLayout(layout_labels_container)
        layout.addWidget(self.container)
        layout.setAlignment(self.container, Qt.AlignHCenter)
        
        #TODO: This is the background around the keyboard widget, that I need to replace/extend for the selection box
        w = ClickableWidget()
        w.setLayout(layout)
        w.clicked.connect(self.on_empty_space_clicked)
        # w.resized.connect(self._resizeEvent)
        self.addWidget(w)

        self.profile_buttons = []
        self.display_layer = 0

        layout_editor.changed.connect(self.rebuild_profiles)

        self.index = 255
        self.index_list = []
        self.tabbed_config = TabbedConfig()

        self.addWidget(self.tabbed_config)

        self.device = None


    def on_empty_space_clicked(self):
        self.container.deselect()
        self.container.update()
        self.index = 255
        self.index_list = []
        self.tabbed_config.update_index(255)


    # def _resizeEvent(self):
    #     width = self.geometry().width()
    #     print(width)
    #     if width > 0:
    #         self.container.update_layout(width)


    #TODO: There's gotta be a better way to update the profile buttons than rebuilding this whole thing every press
    def rebuild_profiles(self):
        # Delete old profile stuff
        for label in self.profile_buttons:
            label.hide()
            label.deleteLater()
        self.profile_buttons = []

        # Create new profile buttons
        for x in range(self.keyboard.max_profiles):
            btn = SquareButton(str(x))

            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(1.667)
            if x < self.keyboard.profiles:
                btn.setCheckable(True)
                btn.clicked.connect(lambda state, idx=x: self.switch_profile(idx))
            else: # Show buttons for unused profiles, but disable them
                btn.setDisabled(True)

            # Check the button for the active profile
            if x == self.keyboard.am_profile:
                btn.setChecked(True)

            self.layout_profiles.addWidget(btn)
            self.profile_buttons.append(btn)

        # Get the config of the selected switch on the new profile
        self.tabbed_config.update_index(self.index, self.index_list)

        # Add buttons to add/delete profiles
        for x in ['+', '-']:
            btn = SquareButton(x)
            btn.setFocusPolicy(Qt.NoFocus)
            if x == '+': 
                if self.keyboard.profiles == self.keyboard.max_profiles:
                    btn.setDisabled(True)
                else:
                    btn.clicked.connect(self.add_profile)
            else: 
                if self.keyboard.profiles == 1:
                    btn.setDisabled(True)
                else:
                    btn.clicked.connect(self.remove_profile)
                    
            self.layout_profiles.addWidget(btn)
            self.profile_buttons.append(btn)

        # Add buttons to toggle the profile layers, limited to 16 layers
        for x in range(min(self.keyboard.layers, 16)):
            btn = SquareButton(str(x))
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(1.667)
            btn.setCheckable(True)
            btn.clicked.connect(lambda state, layer=x: self.keyboard.toggle_profile_layers(self.keyboard.am_profile, layer))
            # Match button states to the state of the profile layers
            btn.setChecked(self.keyboard.profile_layers[self.keyboard.am_profile] & (1 << x))
            self.layout_layers.addWidget(btn)
            self.profile_buttons.append(btn)

        for x in range(0, 2):
            btn = SquareButton("-") if x else SquareButton("+")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCheckable(False)
            btn.clicked.connect(lambda state, idx=x: self.adjust_size(idx))
            self.layout_size.addWidget(btn)
            self.profile_buttons.append(btn)

    def adjust_size(self, minus):
        if minus:
            self.container.set_scale(self.container.get_scale() - 0.1)
        else:
            self.container.set_scale(self.container.get_scale() + 0.1)
        self.rebuild_profiles()
        self.refresh_profile_display()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.tabbed_config.rebuild(self.keyboard)
            self.container.set_keyboard(self.keyboard)

            # Build the profile layout
            self.refresh_profile_display()
            self.rebuild_profiles()

        self.container.setEnabled(self.valid())


    # Only return valid if analog matrix is enabled on the keyboard
    def valid(self):
        return isinstance(self.device, VialKeyboard) and self.device.keyboard and self.device.keyboard.am_enabled

    def save_layout(self):
        return self.keyboard.save_analog_matrix()

    def restore_layout(self, data):
        if json.loads(data.decode("utf-8")).get("uid") != self.keyboard.keyboard_id:
            ret = QMessageBox.question(self.widget(), "",
                                       tr("AnalogMatrixEditor", "Saved config belongs to a different keyboard,"
                                                          " are you sure you want to continue?"),
                                       QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.keyboard.restore_analog_matrix(data)
        self.refresh_profile_display()
        self.rebuild_profiles()


    def code_for_widget(self, widget):
        if widget.desc.row is not None:
            return self.keyboard.layout[(self.display_layer, widget.desc.row, widget.desc.col)]
        else:
            return self.keyboard.encoder_layout[(self.display_layer, widget.desc.encoder_idx,
                                                 widget.desc.encoder_dir)]
        

    def refresh_profile_display(self):
        """ Refresh text on key widgets to display data corresponding to current layer """

        self.container.update_layout()

        for idx, btn in enumerate(self.profile_buttons):
            btn.setEnabled(idx != self.keyboard.am_profile)
            btn.setChecked(idx == self.keyboard.am_profile)

        #NOTE: Removing this keeps the keycodes from rendering at all, since this is called on init too
        for widget in self.container.widgets:
            code = self.code_for_widget(widget)
            KeycodeDisplay.display_keycode(widget, code)
        self.container.update()
        self.container.updateGeometry()


    def switch_profile(self, idx):
        self.keyboard.am_profile = idx
        self.keyboard.set_active_profile(idx)
        
        # Show the keycodes for the lowest assigned layer
        layer = 0
        assigned_layer = False
        layers = self.keyboard.profile_layers[self.keyboard.am_profile]
        for layer in range(self.keyboard.layers):
            if (1 << layer) & layers:
                self.display_layer = layer
                assigned_layer = True
                break
        if not assigned_layer:
            self.display_layer = 0

        self.refresh_profile_display()
        self.rebuild_profiles()

    def add_profile(self):
        if self.keyboard.profiles < self.keyboard.max_profiles:
            self.keyboard.profiles += 1
            self.keyboard.set_used_profiles(self.keyboard.profiles)
            self.rebuild_profiles()

    def remove_profile(self):
        # If the currently selected profile was deleted, select profile 0
        if self.keyboard.am_profile == self.keyboard.profiles - 1:
            self.keyboard.am_profile = 0

        if self.keyboard.profiles > 1:
            self.keyboard.profiles -= 1
            if self.keyboard.am_config['default_profile'] > self.keyboard.profiles - 1:
                # If the default profile was deleted, set it to 0
                self.keyboard.am_config['default_profile'] = 0
                self.keyboard.set_default_profile(0)
            self.keyboard.set_used_profiles(self.keyboard.profiles)
            self.rebuild_profiles()

    def on_key_clicked(self):
        """ Called when a key on the keyboard widget is clicked """

        self.index_list = []
        if self.container.active_key is None:
            self.index = 255
        else:
            self.index = self.keyboard.matrix_to_num[self.container.active_key.desc.row][self.container.active_key.desc.col]
            for key in self.container.active_key_list:
                self.index_list.append(self.keyboard.matrix_to_num[key.desc.row][key.desc.col])
        self.tabbed_config.update_index(self.index, self.index_list)

    def on_key_deselected(self):
        self.index = 255
        self.tabbed_config.update_index(255)


#MARK: Options
class AMIntegerOption(IntegerOption):
    def reload(self, keyboard):
        value = keyboard.saved_values[self.qsid]
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)

class FloatOption(GenericOption):
    def __init__(self, option, container):
        super().__init__(option, container)
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setMinimum(option["min"])
        self.spinbox.setMaximum(option["max"])
        self.spinbox.setSingleStep(option["step"])
        self.spinbox.valueChanged.connect(self.on_change)
        self.container.addWidget(self.spinbox, self.row, 1)

    def reload(self, keyboard):
        value = keyboard.saved_values[self.qsid]
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)

    def value(self):
        return self.spinbox.value()

    def delete(self):
        super().delete()
        self.spinbox.hide()
        self.spinbox.deleteLater()

    
class ComboboxOption(GenericOption):
    def __init__(self, option, container):
        super().__init__(option, container)
        self.combobox = QComboBox()
        self.combobox.addItems(option['options'])
        self.combobox.currentIndexChanged.connect(self.on_change)
        self.container.addWidget(self.combobox, self.row, 1)

    def reload(self, keyboard):
        value = keyboard.saved_values[self.qsid]
        self.combobox.blockSignals(True)
        self.combobox.setCurrentIndex(value)
        self.combobox.blockSignals(False)

    def value(self):
        return self.combobox.currentIndex()

    def delete(self):
        super().delete()
        self.combobox.hide()
        self.combobox.deleteLater()
        

#TODO: Do I want to set this in the settings tab, or in the tabbed config?
#      -Could add a combobox to the settings section in the tab
#       -Would need to keep track of the amount of keys defined per option, and only show available types

# class MatrixOption(GenericOption):
#     def __init__(self, option, container):
#         super().__init__(option, container)
#         self.spinbox = QLineEdit()
#         self.spinbox.valueChanged.connect(self.on_change)
#         self.container.addWidget(self.spinbox, self.row, 1)

#     def reload(self, keyboard):
#         value = keyboard.saved_values[self.qsid]
#         self.spinbox.blockSignals(True)
#         self.spinbox.setValue(value)
#         self.spinbox.blockSignals(False)

#     def value(self):
#         return self.spinbox.value()

#     def delete(self):
#         super().delete()
#         self.spinbox.hide()
#         self.spinbox.deleteLater()


#MARK: Settings
#TODO: The scrollbar doesn't work, the widget inside just gets smaller and smaller
#      The values aren't applied ever
#      The values aren't grabbed correctly, probably aren't even actually available at this point
class AnalogMatrixSettings(BasicEditor):
    def __init__(self):
        super().__init__()

        self.contents = []
        self.keyboard = None
        self.options = []
        
        self.settings_widget = QScrollArea()
        self.settings_widget.setStyleSheet("QScrollArea { background-color:transparent; }")
        self.settings_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.settings_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_widget.setWidgetResizable(True)

        self.addWidget(self.settings_widget)
        self.container = QGridLayout()
        self.settings_widget.setLayout(self.container)
        self.container.setAlignment(Qt.AlignCenter)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton(tr("QmkSettings", "Save"))
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save_settings)
        buttons.addWidget(self.btn_save)
        self.btn_update = QPushButton(tr("QmkSettings", "Update"))
        self.btn_update.setEnabled(False)
        self.btn_update.clicked.connect(self.update_settings)
        buttons.addWidget(self.btn_update)
        self.btn_undo = QPushButton(tr("QmkSettings", "Undo"))
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.reload_settings)
        buttons.addWidget(self.btn_undo)
        self.addLayout(buttons)


    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.reload_settings()

        self.container.setEnabled(self.valid())


    def recreate_gui(self):
        for option in self.options:
            if isinstance(option, QLabel):
                option.hide()
                option.deleteLater()
            else:
                option.delete()
        self.options.clear()

        for option in self.keyboard.am_settings.values():
            if option['type'] == 'divider':
                # Change the label style to better act as a divider
                opt = QLabel(f"<b>{option['title']}</b>")
                opt.setMinimumHeight(28)
                opt.setAlignment(Qt.AlignBottom)
                self.container.addWidget(opt, self.container.rowCount(), 0)

            elif option['type'] == 'integer':
                opt = AMIntegerOption(option, self.container)
                opt.changed.connect(self.on_change)

            #TODO: Currently unused, but will need to make AMBool to get the correct values
            elif option['type'] == 'boolean':
                opt = BooleanOption(option, self.container)
                opt.changed.connect(self.on_change)

            elif option['type'] == 'float':
                opt = FloatOption(option, self.container)
                opt.changed.connect(self.on_change)

            elif option['type'] == 'combo':
                opt = ComboboxOption(option, self.container)
                opt.changed.connect(self.on_change)

            #TODO: Add type that is just a series of buttons toggling bits -> prio profiles

            else:
                continue
            
            self.options.append(opt)
        

    def reload_settings(self):
        self.recreate_gui()

        for option in self.options:
            if isinstance(option, QLabel): continue

            option.reload(self.keyboard)

        self.on_change()

        self.btn_save.setEnabled(False)
        self.btn_undo.setEnabled(False)
        self.btn_update.setEnabled(True)
                

    def on_change(self):
        for field in self.options:
            if isinstance(field, QLabel): continue

            self.keyboard.setting_values[field.qsid] = field.value()

        self.btn_update.setEnabled(True)
        self.btn_undo.setEnabled(True)


    # Only return valid if analog matrix is enabled on the keyboard
    def valid(self):
        return isinstance(self.device, VialKeyboard) and self.device.keyboard and self.device.keyboard.am_enabled
    
    # Save the updated settings to eeprom
    def save_settings(self):
        self.btn_save.setEnabled(False)

        for qsid, value in enumerate(self.keyboard.setting_values):
            self.keyboard.saved_values[qsid] = value

        self.keyboard.send_save_config()

    # Send the changes to the keyboard
    def update_settings(self):
        self.btn_update.setEnabled(False)
        self.btn_save.setEnabled(True)

        for qsid, value in enumerate(self.keyboard.setting_values):
            if self.keyboard.saved_values[qsid] != value:
                if qsid == 0:
                    self.keyboard.set_default_profile(value)
                elif qsid == 1:
                    self.keyboard.set_profile_switch_mode(value)

                elif qsid == 2:
                    self.keyboard.set_deadzone('top_deadzone', value)
                elif qsid == 3:
                    self.keyboard.set_deadzone('bottom_deadzone', value)
                elif qsid == 4:
                    self.keyboard.set_deadzone('smoothing', value)
                elif qsid == 5:
                    self.keyboard.set_deadzone('top_mult', value)
                elif qsid == 6:
                    self.keyboard.set_deadzone('right_mult', value)
                elif qsid == 7:
                    self.keyboard.set_deadzone('slave_mult', value)

                # Filter strengths, currently not implemented
                elif qsid == 8:
                    pass
                elif qsid == 9:
                    pass
                elif qsid == 10:
                    pass

                elif qsid == 11:
                    self.keyboard.set_priority_profiles(value)
                elif qsid == 12:
                    self.keyboard.set_priority_level(value)

                elif qsid == 13:
                    self.keyboard.set_dynamic_calibration('dc_switch_num', value)
                elif qsid == 14:
                    self.keyboard.set_dynamic_calibration('dc_delta', value)
                elif qsid == 15:
                    self.keyboard.set_dynamic_calibration('dc_factor', value)

                elif qsid == 16:
                    self.keyboard.set_deadzone('top_joystick_deadzone', value)
                elif qsid == 17:
                    self.keyboard.set_deadzone('bottom_joystick_deadzone', value)
            


#MARK: Keyboard widget
class AMKeyboardWidget(KeyboardWidget):
    def __init__(self, layout_editor, keyboard):
        super().__init__(layout_editor)
        #TODO: Size policy is ignored
        # self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.keyboard = keyboard
        self.active_key_list = []
        self.selected_list = []
        self.rubberband_origin = QPoint()
        self.rubberband = QRubberBand(QRubberBand.Rectangle, self)
        self.selection_mode = BOX_SELECTION

        #TODO: Instead of setting this to a fixed value, update this according to the bounds of the parent widget
        #->Set the parent to be stretched, then set this value to the difference between the key center and the widget center / 2
        self.widget_padding = 150
        # self.widget_padding = 0
        # self.parent_width = 0

        # Mass select shortcut actions
        self.select_all_action = QAction(self)
        self.select_all_action.setShortcuts(["Ctrl+A", "Ctrl+Shift+A"])
        self.select_all_action.triggered.connect(lambda _: self.select_keys('all'))
        self.addAction(self.select_all_action)
        self.select_left_action = QAction(self)
        self.select_left_action.setShortcut("Ctrl+Shift+L")
        self.select_left_action.triggered.connect(lambda _: self.select_keys('left'))
        self.addAction(self.select_left_action)
        self.select_right_action = QAction(self)
        self.select_right_action.setShortcut("Ctrl+Shift+R")
        self.select_right_action.triggered.connect(lambda _: self.select_keys('right'))
        self.addAction(self.select_right_action)
        self.deselect_action = QAction(self)
        self.deselect_action.setShortcut("Esc")
        self.deselect_action.triggered.connect(self.deselect)
        self.addAction(self.deselect_action)


    def set_keyboard(self, keyboard):
        self.keyboard = keyboard


    def select_keys(self, type):
        self.active_key_list = []

        if type == 'all': key_range = (0, self.keyboard.am_config['total_switch_num'])
        elif type == 'left': key_range = (0, self.keyboard.am_config['switch_num'])
        elif type == 'right': key_range = (self.keyboard.am_config['switch_num'], self.keyboard.am_config['total_switch_num'])

        matrix_to_num = self.keyboard.matrix_to_num

        for key in self.widgets:
            if matrix_to_num[key.desc.row][key.desc.col] in range(key_range[0], key_range[1]):
                self.active_key_list.append(key)

        if self.active_key is None:
            self.active_key = self.active_key_list[0]

        self.clicked.emit()
    

    def deselect(self):
        if self.active_key is not None:
            self.active_key = None
            self.active_key_list = []
            self.deselected.emit()
            self.update()


    def mousePressEvent(self, ev):
        if not self.enabled:
            return

        #TODO: The rubberband currently only works inside the keyboard portion, the space around it isn't covered by it
        #       ->The easiest way around this is probably to just expand the keyboard widget in x direction to the edges
        if ev.button() == Qt.LeftButton:
            self.rubberband_origin = QPoint(ev.pos())
            self.rubberband.show()
            # if self.selection_mode == BOX_SELECTION:
            #TODO: Make a path selection tool working without drawing the rectangle
            self.rubberband.setGeometry(QRect(self.rubberband_origin, QSize()))
            # else:

        self.active_key, self.active_mask = self.hit_test(ev.pos())
        if self.active_key is not None:
            # If CTRL is held, append to the list instead of overwriting
            if (QApplication.keyboardModifiers() & Qt.ControlModifier):
                if self.active_key not in self.active_key_list:
                    self.active_key_list.append(self.active_key)

            # If SHIFT is held, select all keys between the two last selected keys
            elif (QApplication.keyboardModifiers() & Qt.ShiftModifier):
                if self.active_key_list == []: self.active_key_list = [self.active_key]
                if self.active_key_list[0] != self.active_key:
                    reverse = False
                    if self.active_key_list[0].desc.row > self.active_key.desc.row: reverse = True
                    elif self.active_key_list[0].desc.row == self.active_key.desc.row and self.active_key_list[0].desc.col > self.active_key.desc.col: reverse = True
                    starting_row = min(self.active_key_list[0].desc.row, self.active_key.desc.row)
                    starting_col = min(self.active_key_list[0].desc.col, self.active_key.desc.col)
                    ending_row = max(self.active_key_list[0].desc.row, self.active_key.desc.row)
                    ending_col = max(self.active_key_list[0].desc.col, self.active_key.desc.col)
                    #TODO: I could simplify this a lot if I could just get the matrix_to_num and compare the indexes
                    for key in self.widgets:
                        if key in self.active_key_list: continue
                        if key.desc.row > starting_row and key.desc.row < ending_row:
                            self.active_key_list.append(key)
                        elif key.desc.row == starting_row and key.desc.row == ending_row and key.desc.col >= starting_col and key.desc.col <= ending_col:
                            self.active_key_list.append(key)
                        elif key.desc.row == starting_row and key.desc.row != ending_row and key.desc.col >= starting_col or key.desc.row == ending_row and key.desc.row != starting_row and key.desc.col <= ending_col:
                            self.active_key_list.append(key)
                    
                    self.active_key_list.sort(reverse=reverse, key=lambda w: (w.desc.y, w.desc.x))

            # If neither modifier is held, only select the newest key
            else:
                self.active_key_list = [self.active_key]

            self.clicked.emit()

        # else:
        #     self.deselected.emit()
        #     self.active_key_list = []
        self.update()


    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if self.active_key is None and self.selected_list == [] and not (QApplication.keyboardModifiers() & Qt.ControlModifier):
                self.deselected.emit()
                self.active_key_list = []

            self.rubberband_origin.setX(0)
            self.rubberband_origin.setY(0)
            #NOTE: The selection doesn't update unless .show/hide is called on the rubberband for some reason
            # if self.selection_mode == BOX_SELECTION:
            self.rubberband.hide()
            for key in self.selected_list:
                if key not in self.active_key_list:
                    self.active_key_list.append(key)
            self.selected_list = []

            # If keys are active but the active_key position is empty, set it to the last selected key
            if self.active_key is None and self.active_key_list != []:
                #TODO: This is currently the highest index key, not the last selected one as intended
                self.active_key = self.active_key_list[-1]

            if self.active_key is not None:
                self.clicked.emit()


    def mouseMoveEvent(self, ev):
        if not self.rubberband_origin.isNull():
            if self.selection_mode == BOX_SELECTION:
                self.rubberband.setGeometry(QRect(self.rubberband_origin, ev.pos()).normalized())

                #NOTE: Top left corner is 0, 0
                # # Check if we're using inclusive or exclusive mode
                if ev.pos().x() < self.rubberband_origin.x():
                    mode = INCLUSIVE_MODE
                    left_x = ev.pos().x() / self.scale
                    right_x = self.rubberband_origin.x() / self.scale
                else:
                    mode = EXCLUSIVE_MODE
                    left_x = self.rubberband_origin.x() / self.scale
                    right_x = ev.pos().x() / self.scale
                top_y = min(self.rubberband_origin.y(), ev.pos().y()) / self.scale
                bottom_y = max(self.rubberband_origin.y(), ev.pos().y()) / self.scale

                self.selected_list = []
                for key in self.widgets:
                    #TODO: Need to find out if these values are the actual position of the widget, i.e. do they take rotation into account?
                    l_x = min(key.polygon.boundingRect().topLeft().x(), key.polygon.boundingRect().bottomLeft().x())
                    r_x = max(key.polygon.boundingRect().topRight().x(), key.polygon.boundingRect().bottomRight().x())
                    t_y = min(key.polygon.boundingRect().topLeft().y(), key.polygon.boundingRect().topRight().y())
                    b_y = max(key.polygon.boundingRect().bottomLeft().y(), key.polygon.boundingRect().bottomRight().y())
                    if mode == INCLUSIVE_MODE:
                        if not (r_x < left_x or l_x > right_x or b_y < top_y or t_y > bottom_y):
                            self.selected_list.append(key)
                    else:
                        #TODO: Need to deselect the active key on exclusive mode, but this doesn't work as intended
                        #      The active index is reset correctly, but the key remains highlighted -> likely a QP problem
                        # Deselect the initially pressed key, as it's not part of the selection in exclusive mode
                        if self.active_key is not None:
                            # self.deselected.emit()
                            self.active_key.active = False
                            self.active_key = None
                            self.clicked.emit()
                            self.update()
                            
                        if left_x < l_x and top_y < t_y and right_x > r_x and bottom_y > b_y:
                            self.selected_list.append(key)


            #NOTE: This mode can be used to select keys by dragging over them instead of using a rectangle
            #       -> Add a button to toggle between them
            #       Need to find a way to select the keys without needing to drag the rubberband though, it currently doesn't work without the show/hide methods
            else:
                for key in self.widgets:
                    if key.polygon.containsPoint(ev.pos()/self.scale, Qt.OddEvenFill):
                        self.active_key_list.append(key)


    # def Geometry(self, geometry):
    #     # self.widget_padding = (geometry[0] - ) // 2
    #     pass
            

    def place_widgets(self):
        scale_factor = self.fontMetrics().height()

        self.widgets = []

        # place common widgets, that is, ones which are always displayed and require no extra transforms
        for widget in self.common_widgets:
            widget.update_position(scale_factor)
            self.widgets.append(widget)

        # top-left position for specific layout
        layout_x = defaultdict(lambda: defaultdict(lambda: 1e6))
        layout_y = defaultdict(lambda: defaultdict(lambda: 1e6))

        # determine top-left position for every layout option
        for widget in self.widgets_for_layout:
            widget.update_position(scale_factor)
            idx, opt = widget.desc.layout_index, widget.desc.layout_option
            p = widget.polygon.boundingRect().topLeft()
            layout_x[idx][opt] = min(layout_x[idx][opt], p.x())
            layout_y[idx][opt] = min(layout_y[idx][opt], p.y())

        # obtain widgets for all layout options now that we know how to shift them
        for widget in self.widgets_for_layout:
            idx, opt = widget.desc.layout_index, widget.desc.layout_option
            if opt == self.layout_editor.get_choice(idx):
                shift_x = layout_x[idx][opt] - layout_x[idx][0]
                shift_y = layout_y[idx][opt] - layout_y[idx][0]
                widget.update_position(scale_factor, -shift_x, -shift_y)
                self.widgets.append(widget)

        # at this point some widgets on left side might be cutoff, or there may be too much empty space
        # calculate top left position of visible widgets and shift everything around
        top_x = top_y = 1e6
        for widget in self.widgets:
            if not widget.desc.decal:
                p = widget.polygon.boundingRect().topLeft()
                top_x = min(top_x, p.x())
                top_y = min(top_y, p.y())
        for widget in self.widgets:
            widget.update_position(widget.scale, widget.shift_x - top_x + self.padding + self.widget_padding,
                                   widget.shift_y - top_y + self.padding)

    #TODO: This sets the bounds of the keyboard widget, if I want to extend it past the necessary bounds for the selection box, I need to hook into this function
    def update_layout(self, parent_width=None):
        """ Updates self.widgets for the currently active layout """

        #TODO: Instead of setting the width like this, set it to the parent width and update the widget_padding appropriately
        # if parent_width is not None:
        #     self.parent_width = parent_width
        #     print(f"Width: {self.width}, parent_width: {parent_width}")

        # determine widgets for current layout
        self.place_widgets()
        self.widgets = list(filter(lambda w: not w.desc.decal, self.widgets))

        self.widgets.sort(key=lambda w: (w.y, w.x))

        # determine maximum width and height of container
        max_w = max_h = 0
        for key in self.widgets:
            p = key.polygon.boundingRect().bottomRight()
            max_w = max(max_w, p.x() * self.scale)
            max_h = max(max_h, p.y() * self.scale)

        #TODO: This doesn't work properly, but might be usable
        # if self.parent_width == 0:
        #     self.width = round(max_w + 2 * self.padding + self.widget_padding)
        # else:
        #     self.width = self.parent_width
        #     self.widget_padding = (self.width - max_w) // 2

        self.width = round(max_w + 2 * self.padding + self.widget_padding)
        self.height = round(max_h + 2 * self.padding)

        self.update()
        self.updateGeometry()


    #NOTE: The weird drawing behaviour almost makes me think that this draws on the highest active widget (the selection rectangle) instead of the keys specifically
    # This is called by the widget itself, when it needs to update
    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing)

        # for regular keycaps
        regular_pen = qp.pen()
        regular_pen.setColor(QApplication.palette().color(QPalette.ButtonText))
        qp.setPen(regular_pen)

        background_brush = QBrush()
        background_brush.setColor(QApplication.palette().color(QPalette.Button))
        background_brush.setStyle(Qt.SolidPattern)

        foreground_brush = QBrush()
        foreground_brush.setColor(QApplication.palette().color(QPalette.Button).lighter(120))
        foreground_brush.setStyle(Qt.SolidPattern)

        mask_brush = QBrush()
        mask_brush.setColor(QApplication.palette().color(QPalette.Button).lighter(Theme.mask_light_factor()))
        mask_brush.setStyle(Qt.SolidPattern)

        # For non-analog keys
        rc_brush = QBrush()
        rc_brush.setColor(QApplication.palette().color(QPalette.Button).darker(250))
        rc_brush.setStyle(Qt.SolidPattern)

        # for currently selected keycap
        active_pen = qp.pen()
        active_pen.setColor(QApplication.palette().color(QPalette.Highlight))
        active_pen.setWidthF(1.5)

        # for the encoder arrow
        extra_pen = regular_pen
        extra_brush = QBrush()
        extra_brush.setColor(QApplication.palette().color(QPalette.ButtonText))
        extra_brush.setStyle(Qt.SolidPattern)

        # for pressed keycaps
        background_pressed_brush = QBrush()
        background_pressed_brush.setColor(QApplication.palette().color(QPalette.Highlight))
        background_pressed_brush.setStyle(Qt.SolidPattern)

        foreground_pressed_brush = QBrush()
        foreground_pressed_brush.setColor(QApplication.palette().color(QPalette.Highlight).lighter(120))
        foreground_pressed_brush.setStyle(Qt.SolidPattern)

        background_on_brush = QBrush()
        background_on_brush.setColor(QApplication.palette().color(QPalette.Highlight).darker(150))
        background_on_brush.setStyle(Qt.SolidPattern)

        foreground_on_brush = QBrush()
        foreground_on_brush.setColor(QApplication.palette().color(QPalette.Highlight).darker(120))
        foreground_on_brush.setStyle(Qt.SolidPattern)

        mask_font = qp.font()
        mask_font.setPointSize(round(mask_font.pointSize() * 0.8))

        for key in self.widgets:
            qp.save()

            qp.scale(self.scale, self.scale)
            qp.translate(key.shift_x, key.shift_y)
            qp.translate(key.rotation_x, key.rotation_y)
            qp.rotate(key.rotation_angle)
            qp.translate(-key.rotation_x, -key.rotation_y)

            #TODO: Update this to highlight all selected keys properly
            #      -While a selection box is used, only the part of the key that is inside it is highlighted correctly
            #       ->This is likely because the painter draws on the highest widget (or something), so only the parts inside the rectangle get updated
            active = key in self.active_key_list or key in self.selected_list

            # draw keycap background/drop-shadow
            qp.setPen(active_pen if active else Qt.NoPen)
            brush = background_brush

            if key.pressed:
                brush = background_pressed_brush
            elif key.on:
                brush = background_on_brush
            qp.setBrush(brush)
            qp.drawPath(key.background_draw_path)

            # draw keycap foreground
            qp.setPen(Qt.NoPen)
            brush = foreground_brush

            #TODO: The current rc brush is kinda ugly, fiddle around with it some more
            row, col = key.desc.row, key.desc.col
            if self.keyboard != None and self.keyboard.am_enabled and self.keyboard.matrix_to_num[row][col] == 255:
                brush = rc_brush
            elif key.pressed:
                brush = foreground_pressed_brush
            elif key.on:
                brush = foreground_on_brush
            qp.setBrush(brush)
            qp.drawPath(key.foreground_draw_path)

            # draw key text
            if key.masked:
                # draw the outer legend
                qp.setFont(mask_font)
                qp.setPen(key.color if key.color else regular_pen)
                qp.drawText(key.nonmask_rect, Qt.AlignCenter, key.text)

                # draw the inner highlight rect
                qp.setPen(active_pen if self.active_key == key and self.active_mask else Qt.NoPen)
                qp.setBrush(mask_brush)
                qp.drawRoundedRect(key.mask_rect, key.corner, key.corner)

                # draw the inner legend
                qp.setPen(key.mask_color if key.mask_color else regular_pen)
                qp.drawText(key.mask_rect, Qt.AlignCenter, key.mask_text)
            else:
                # draw the legend
                qp.setPen(key.color if key.color else regular_pen)
                qp.drawText(key.text_rect, Qt.AlignCenter, key.text)

            # draw the extra shape (encoder arrow)
            qp.setPen(extra_pen)
            qp.setBrush(extra_brush)
            qp.drawPath(key.extra_draw_path)

            qp.restore()

        qp.end()

