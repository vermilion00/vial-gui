# SPDX-License-Identifier: GPL-2.0-or-later
import json

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QMessageBox, QWidget
from PyQt5.QtCore import Qt, pyqtSignal

from any_keycode_dialog import AnyKeycodeDialog
from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget, EncoderWidget
from keycodes.keycodes import Keycode
from widgets.square_button import SquareButton
from tabbed_keycodes import TabbedKeycodes, keycode_filter_masked
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard


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
        profile_label = QLabel(tr("AnalogMatrixEditor", "Profile"))

        layout_labels_container = QHBoxLayout()
        layout_labels_container.addWidget(profile_label)
        layout_labels_container.addLayout(self.layout_profiles)
        layout_labels_container.addStretch()
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
        self.current_profile = 0

        layout_editor.changed.connect(self.on_layout_changed)

        self.container.anykey.connect(self.on_any_keycode)

        #TODO: Since this is probably the bottom tray, I need to change this to the config
        # self.tabbed_keycodes = TabbedKeycodes()
        # self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_changed)
        # self.tabbed_keycodes.anykey.connect(self.on_any_keycode)

        # self.addWidget(w)
        # self.addWidget(self.tabbed_keycodes)

        self.device = None
        #TODO: Is this for the any keycode? If so, I can remove this
        # KeycodeDisplay.notify_keymap_override(self)

    def on_empty_space_clicked(self):
        self.container.deselect()
        self.container.update()

    #TODO: Change this for the various config options
    def on_keycode_changed(self, code):
        self.set_key(code)

    #TODO: What is this? Is this responsible for showing the layer buttons? If so, change this to profiles
    def rebuild_profiles(self):
        # delete old layer labels
        for label in self.profile_buttons:
            label.hide()
            label.deleteLater()
        self.profile_buttons = []

        # create new layer labels
        #TODO: Need to save profile data to keyboard object, on pull that here
        #TODO: Changing this from layers to profiles doesn't work, the layer num is still used
        for x in range(self.keyboard.profiles):
            btn = SquareButton(str(x))
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(1.667)
            btn.setCheckable(True)
            btn.clicked.connect(lambda state, idx=x: self.switch_profile(idx))
            self.layout_profiles.addWidget(btn)
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

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

            # get number of layers
            self.rebuild_profiles()

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.current_profile = 0
            self.on_layout_changed()

            self.tabbed_keycodes.recreate_keycode_buttons()
            TabbedKeycodes.tray.recreate_keycode_buttons()
            self.refresh_profile_display()
        self.container.setEnabled(self.valid())

    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def save_layout(self):
        return self.keyboard.save_layout()

    def restore_layout(self, data):
        if json.loads(data.decode("utf-8")).get("uid") != self.keyboard.keyboard_id:
            ret = QMessageBox.question(self.widget(), "",
                                       tr("AnalogMatrixEditor", "Saved config belongs to a different keyboard,"
                                                          " are you sure you want to continue?"),
                                       QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.keyboard.restore_layout(data)
        self.refresh_profile_display()

    # def on_any_keycode(self):
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

    #TODO: What is this?
    def code_for_widget(self, widget):
        if widget.desc.row is not None:
            return self.keyboard.layout[(self.current_profile, widget.desc.row, widget.desc.col)]
        else:
            return self.keyboard.encoder_layout[(self.current_profile, widget.desc.encoder_idx,
                                                 widget.desc.encoder_dir)]

    #TODO: Update this for profiles instead
    def refresh_profile_display(self):
        """ Refresh text on key widgets to display data corresponding to current profile """

        self.container.update_layout()

        for idx, btn in enumerate(self.profile_buttons):
            btn.setEnabled(idx != self.current_profile)
            btn.setChecked(idx == self.current_profile)

        for widget in self.container.widgets:
            code = self.code_for_widget(widget)
            #TODO: Don't need this
            KeycodeDisplay.display_keycode(widget, code)
        self.container.update()
        self.container.updateGeometry()

    def switch_profile(self, idx):
        #TODO: What does this do? I think it just deselects all keys if the profile is switched
        #      The keys are still switched off, something else probably does the same thing
        # self.container.deselect()
        self.current_profile = idx
        self.refresh_profile_display()

    #TODO: Remove this and call the appropriate config instead -> instead of keycode, it should take the type of config and the value
    def set_key(self, keycode):
        """ Change currently selected key to provided keycode """

        if self.container.active_key is None:
            return
        
        #TODO: This should accept index?
        self.set_key_matrix(keycode)

        self.container.select_next()

    def set_key_matrix(self, keycode):
        #TODO: This accepts only a single key, either process all active keys in here or call this repeatedly
        p, r, c = self.current_profile, self.container.active_key.desc.row, self.container.active_key.desc.col

        if r >= 0 and c >= 0:
            #TODO: Since we don't need keycodes here, change this
            # if masked, ensure that this is a byte-sized keycode
            # if self.container.active_mask:
            #     if not Keycode.is_basic(keycode):
            #         return
            #     kc = Keycode.find_outer_keycode(self.keyboard.layout[(l, r, c)])
            #     if kc is None:
            #         return
            #     keycode = kc.qmk_id.replace("(kc)", "({})".format(keycode))

            self.keyboard.set_key(p, r, c, keycode)
            self.refresh_profile_display()

    #TODO: This doesn't seem to set the active key
    def on_key_clicked(self):
        """ Called when a key on the keyboard widget is clicked """
        # self.refresh_profile_display()
        # if self.container.active_mask:
        #     self.tabbed_keycodes.set_keycode_filter(keycode_filter_masked)
        # else:
        #     self.tabbed_keycodes.set_keycode_filter(None)
        pass

    def on_key_deselected(self):
        self.tabbed_keycodes.set_keycode_filter(None)

    def on_layout_changed(self):
        if self.keyboard is None:
            return

        self.refresh_profile_display()
        self.keyboard.set_layout_options(self.layout_editor.pack())

    def on_keymap_override(self):
        self.refresh_profile_display()
