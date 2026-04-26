# SPDX-License-Identifier: GPL-2.0-or-later
import json

from PyQt5.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout, QMessageBox, QWidget
from PyQt5.QtCore import Qt, pyqtSignal

from any_keycode_dialog import AnyKeycodeDialog
from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget, EncoderWidget
from keycodes.keycodes import Keycode
from widgets.square_button import SquareButton
from tabbed_keycodes import TabbedKeycodes
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard
from protocol.analog_matrix import ProtocolAnalogMatrix, SWITCH_PRESS_HEIGHT, SWITCH_RELEASE_HEIGHT, SWITCH_PRESS_DISTANCE, SWITCH_RELEASE_DISTANCE, SWITCH_MODE, SWITCH_PRIORITY
from widgets.tabbed_config import TabbedConfig

class ClickableWidget(QWidget):

    clicked = pyqtSignal()

    def mousePressEvent(self, evt):
        super().mousePressEvent(evt)
        self.clicked.emit()


class AnalogMatrixEditor(BasicEditor):

    def __init__(self, layout_editor):
        super().__init__()

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

        # contains the actual keyboard
        self.container = KeyboardWidget(layout_editor)
        self.container.clicked.connect(self.on_key_clicked)
        #TODO: Since I want to be able to select multiple keys, I probably need to hook into this
        self.container.deselected.connect(self.on_key_deselected)

        layout = QVBoxLayout()
        layout.addLayout(layout_labels_container)
        layout.addWidget(self.container)
        layout.setAlignment(self.container, Qt.AlignHCenter)
        w = ClickableWidget()
        w.setLayout(layout)
        w.clicked.connect(self.on_empty_space_clicked)

        self.profile_buttons = []
        self.keyboard = None

        self.display_layer = 0

        layout_editor.changed.connect(self.rebuild_profiles)

        self.index = 255
        self.tabbed_config = TabbedConfig()

        self.addWidget(w)
        self.addWidget(self.tabbed_config)

        self.device = None
        #TODO: Is this for the any keycode? If so, I can remove this
        # KeycodeDisplay.notify_keymap_override(self)
        # self.container.anykey.connect(self.on_any_keycode)

    #TODO: Since I want to be able to drag a box from the empty space, I might need to hook into this
    def on_empty_space_clicked(self):
        self.container.deselect()
        self.container.update()
        self.index = 255
        self.tabbed_config.update_index(255)


    #TODO: There's gotta be a better way to update the profile buttons than rebuilding this whole thing every press
    #TODO: The checked stuff etc doesn't work the first time around, probably because it's called too early? Call it again every time we open the tab I guess
    #      It is aware of the am_config though, and has the correct config pulled. Is it because those things can't apply when they're not rendered? Wouldn't really make sense
    def rebuild_profiles(self):
        # Delete old layer labels
        for label in self.profile_buttons:
            label.hide()
            label.deleteLater()
        self.profile_buttons = []

        # Create new profile buttons
        #TODO: Remove the +5 when done testing
        for x in range(self.keyboard.max_profiles + 5):
            btn = SquareButton(str(x))

            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(1.667)
            if x < self.keyboard.profiles:
                btn.setCheckable(True)
                btn.clicked.connect(lambda state, idx=x: self.switch_profile(idx))
            else: # Show buttons for deleted profiles, but apply a different style and disable them
                btn.setDisabled(True)
                btn.setCheckable(False)

            # Auto-enable the button for the active profile
            if x == self.keyboard.am_profile:
                btn.setChecked(True)

            self.layout_profiles.addWidget(btn)
            self.profile_buttons.append(btn)

            # Get the config of the selected switch on the new profile
            self.tabbed_config.update_index(self.index)

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

        #NOTE: This sets zoom buttons
        for x in range(0,2):
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
        self.refresh_profile_display()
        self.rebuild_profiles()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            #NOTE: am_enabled is only set after this is called
            self.keyboard = device.keyboard

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.refresh_profile_display()
            
            # Build the profile layout
            self.rebuild_profiles()

            self.tabbed_config.rebuild(self.keyboard)

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

    #NOTE: This gets the keycode for the provided widget (each widget here represents a key)
    #TODO: the display layer is set after this is called
    def code_for_widget(self, widget):
        if widget.desc.row is not None:
            return self.keyboard.layout[(self.display_layer, widget.desc.row, widget.desc.col)]
        else:
            return self.keyboard.encoder_layout[(self.display_layer, widget.desc.encoder_idx,
                                                 widget.desc.encoder_dir)]

    #TODO: Update this for profiles instead
    def refresh_profile_display(self):
        """ Refresh text on key widgets to display data corresponding to current layer """

        #TODO: Instead of updating the text on the switches, it should update the profile related icons instead (key mode, prio key etc)
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

    #TODO: Need to draw the keycodes after this is called, since the display layer is set too late currently
    def switch_profile(self, idx):
        #TODO: What does this do? I think it just deselects all keys if the profile is switched
        #      The keys are still switched off, something else probably does the same thing
        # self.container.deselect()

        self.keyboard.am_profile = idx
        self.keyboard.set_active_profile(idx)
        
        #TODO: This currently isn't used anywhere, as the keycodes are painted before this is assigned
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

        self.rebuild_profiles()

    def add_profile(self):
        if self.keyboard.profiles < self.keyboard.max_profiles:
            self.keyboard.profiles += 1
            self.keyboard.set_used_profiles(self.keyboard.profiles)
            self.rebuild_profiles()

    def remove_profile(self):
        if self.keyboard.am_profile == self.keyboard.profile - 1:
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

        self.index = self.keyboard.matrix_to_num[self.container.active_key.desc.row][self.container.active_key.desc.col]
        self.tabbed_config.update_index(self.index)

    #TODO: This is called when the empty space around the keyboard is pressed
    #TODO: Will need to hook into this to be able to drag select keys
    def on_key_deselected(self):
        self.index = 255
        self.tabbed_config.update_index(255)
        

    #TODO: Compiling without this doesn't work
    # def on_keymap_override(self):
    #     self.refresh_profile_display()


    #TODO: Do I need to have this in incase of an any key in the keymap, or can I remove this?
    #      I'm pretty sure this is just to set the new action, which I don't need here
    # def on_any_keycode(self):
    #     print("on_any_keycode")
    #     if self.container.active_key is None:
    #         return
    #     current_code = self.code_for_widget(self.container.active_key)
    #     if self.container.active_mask:
    #         kc = Keycode.find_inner_keycode(current_code)
    #         current_code = kc.qmk_id

    #     self.dlg = AnyKeycodeDialog(current_code)
    #     self.dlg.finished.connect(self.on_dlg_finished)
    #     self.dlg.setModal(True)
    #     self.dlg.show()

    # def on_dlg_finished(self, res):
    #     if res > 0:
    #         self.on_keycode_changed(self.dlg.value)

    
    # def on_layout_changed(self):
    #     if self.keyboard is None:
    #         return

    #     self.refresh_profile_display()
        # self.keyboard.set_layout_options(self.layout_editor.pack())