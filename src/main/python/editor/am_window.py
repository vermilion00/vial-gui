# SPDX-License-Identifier: GPL-2.0-or-later
import json

from PyQt5.QtCore import Qt, QSize, QRect, QPointF, pyqtSignal, QEvent, QRectF, QPoint
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QTransform, QBrush, QPolygonF, QPalette
from PyQt5.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QMessageBox, QWidget, QSpinBox,  QToolTip, QApplication, QRubberBand
from themes import Theme

from editor.basic_editor import BasicEditor
from editor.qmk_settings import BooleanOption, IntegerOption
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

    def mousePressEvent(self, evt):
        super().mousePressEvent(evt)
        self.clicked.emit()


class AnalogMatrixEditor(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()

        self.keyboard = None

        self.layout_editor = layout_editor
        # self.layout_editor.addStretch()

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
        self.container.clicked.connect(self.on_key_clicked)
        self.container.deselected.connect(self.on_key_deselected)

        layout = QVBoxLayout()
        #TODO: Even with the stretch, the layout doesn't extend past the keyboard widget
        # layout.addStretch()
        layout.addLayout(layout_labels_container)
        layout.addWidget(self.container)
        layout.setAlignment(self.container, Qt.AlignHCenter)
        #TODO: This is the background around the keyboard widget, that I need to replace/extend for the selection box
        w = ClickableWidget()
        w.setLayout(layout)
        w.clicked.connect(self.on_empty_space_clicked)
        self.addWidget(w)

        self.profile_buttons = []
        self.display_layer = 0

        layout_editor.changed.connect(self.rebuild_profiles)

        self.index = 255
        self.index_list = []
        self.tabbed_config = TabbedConfig()

        self.addWidget(self.tabbed_config)

        self.device = None

    #TODO: Since I want to be able to drag a box from the empty space, I might need to hook into this
    def on_empty_space_clicked(self):
        self.container.deselect()
        self.container.update()
        self.index = 255
        self.index_list = []
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
        # self.refresh_profile_display()
        # self.rebuild_profiles()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            #NOTE: am_enabled is only set after this is called
            self.keyboard = device.keyboard

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.tabbed_config.rebuild(self.keyboard)
            self.container.set_keyboard(self.keyboard)

            # Build the profile layout
            self.rebuild_profiles()

            self.refresh_profile_display()

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

        self.index_list = []
        if self.container.active_key is None:
            self.index = 255
        else:
            self.index = self.keyboard.matrix_to_num[self.container.active_key.desc.row][self.container.active_key.desc.col]
            for key in self.container.active_key_list:
                self.index_list.append(self.keyboard.matrix_to_num[key.desc.row][key.desc.col])
        self.tabbed_config.update_index(self.index, self.index_list)

    #NOTE: This is called when the empty space around the keyboard is pressed
    #TODO: Will need to hook into this to be able to drag select keys
    def on_key_deselected(self):
        self.index = 255
        self.tabbed_config.update_index(255)


class AnalogMatrixSettings(BasicEditor):
    def __init__(self):
        super().__init__()

        self.contents = []

        self.keyboard = None

        # self.layout = QVBoxLayout()
        # self.addLayout(self.layout)
        # self.contents.append(self.layout)
        self.options = []

        self.container = QGridLayout()
        self.addLayout(self.container)
    
        #TODO: Make sure the qsid doesn't fuck it up
        #      Is it supposed to be the value? Do I need to set it to the current state, or is it an actual ID?
        #      These are pulled from a json
        options = {
            'top_deadzone': {'title': 'Top Deadzone', 'type': 'integer', 'min': 0, 'max': 255, 'qsid': 0, 'width': 1},
            'bottom_deadzone': {'title': 'Bottom Deadzone', 'type': 'integer', 'min': 0, 'max': 255, 'qsid': 1, 'width': 1}
        }
        
        for key in options.keys():
            if options[key] == 'integer':
                self.options = IntegerOption(key, self.container)
                # self.options.append(IntegerOption(key, self.container))
                # self.container.addWidget(self.options[-1])
                self.container.addWidget(self.options[-1])
            elif options[key] == 'boolean':
                self.options.append(BooleanOption(key, self.container))
                self.container.addWidget(self.options[-1])


    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

        self.container.setEnabled(self.valid())


    # Only return valid if analog matrix is enabled on the keyboard
    def valid(self):
        return isinstance(self.device, VialKeyboard) and self.device.keyboard and self.device.keyboard.am_enabled


#TODO: Make this a thing
class AMKeyboardWidget(KeyboardWidget):
    def __init__(self, layout_editor, keyboard):
        super().__init__(layout_editor)
        self.keyboard = keyboard
        self.active_key_list = []
        self.selected_list = []
        self.rubberband = QRubberBand(QRubberBand.Rectangle, self)
        self.rubberband_origin = QPoint()
        self.selection_mode = BOX_SELECTION


    def set_keyboard(self, keyboard):
        self.keyboard = keyboard

    
    def deselect(self):
        if self.active_key is not None:
            self.active_key = None
            self.active_key_list = []
            self.deselected.emit()
            self.update()


    def mousePressEvent(self, ev):
        if not self.enabled:
            return
        
        #TODO: How do I want to differentiate between presses and drags?
        #      -I could make it so that drags only register when I start it in an empty space, would be the easiest but annoying
        #      -I could make it so that the selection only triggers on release when no dragging is happening, also annoying
        #      -The best option would be to select the key instantly but also allow for dragging simultaneously
        #           -The selection is still evaluated when pressed
        #           -If a drag is active, re-evaluate the selection every move update
        #           -Deactivate the window in the release function
        #           ->This option would mean that the deselect function is called in the release event, if the drag didn't select any keys
        #               -Actually, do I want to be able to add keys to an existing selection with the drag, or should it just clear when started in empty space?

        #TODO: The rubberband currently only works inside the keyboard portion, the space around it isn't covered by it
        #       ->The easiest way around this is probably to just expand the keyboard widget in x direction to the edges
        if ev.button() == Qt.LeftButton:
            self.rubberband_origin = QPoint(ev.pos())
            if self.selection_mode == BOX_SELECTION:
                self.rubberband.show()
                self.rubberband.setGeometry(QRect(self.rubberband_origin, QSize()))

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
            if self.active_key is None and self.selected_list == []:
                self.deselected.emit()
                self.active_key_list = []

            self.rubberband_origin.setX(0)
            self.rubberband_origin.setY(0)
            #NOTE: The selection doesn't update unless .show/hide is called on the rubberband for some reason
            if self.selection_mode == BOX_SELECTION:
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

        # print(self.active_key_list)


    def mouseMoveEvent(self, ev):
        if not self.rubberband_origin.isNull():
            if self.selection_mode == BOX_SELECTION:
                self.rubberband.setGeometry(QRect(self.rubberband_origin, ev.pos()).normalized())

                #TODO: When dragging, the keys should only be added on release
                # Top left corner is 0, 0
                # # Check if we're using inclusive or exclusive mode
                if ev.pos().x() < self.rubberband_origin.x():
                    mode = EXCLUSIVE_MODE
                    left_x = ev.pos().x()
                    right_x = self.rubberband_origin.x()
                else:
                    mode = INCLUSIVE_MODE
                    left_x = self.rubberband_origin.x()
                    right_x = ev.pos().x()
                top_y = min(self.rubberband_origin.y(), ev.pos().y())
                bottom_y = max(self.rubberband_origin.y(), ev.pos().y())

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
                            self.active_key.active = False
                            self.active_key = None
                            self.clicked.emit()
                        if left_x < l_x and top_y < t_y and right_x > r_x and bottom_y > b_y:
                            self.selected_list.append(key)


            #NOTE: This mode can be used to select keys by dragging over them instead of using a rectangle
            #       -> Add a button to toggle between them
            else:
                for key in self.widgets:
                    if key.polygon.containsPoint(ev.pos()/self.scale, Qt.OddEvenFill):
                        self.active_key_list.append(key)
            
            # print(self.active_key_list)

            # Get all widgets inside the selection
            #NOTE: I can get the top left corner coordinates via key.x and key.y, how do I get the size?
            # for key in self.widgets:
                
            # Propagate the new selection to the child classes


    #NOTE: The weird drawing behaviour almost makes me think that this draws on the highest active widget (the selection rectangle) instead of the keys specifically
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
            active = key.active or key in self.active_key_list or key in self.selected_list

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

            if key.pressed:
                brush = foreground_pressed_brush
            elif key.on:
                brush = foreground_on_brush
            qp.setBrush(brush)
            qp.drawPath(key.foreground_draw_path)

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

