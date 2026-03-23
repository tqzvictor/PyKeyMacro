import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import threading
import time
from pynput import keyboard

DEFAULT_FILE = "default.json"

# --- 智能显示格式化工具 ---


def format_key_for_display(key_str):
    """将底层按键名称美化为通俗易懂的显示格式"""
    if key_str.startswith("Key."):
        name = key_str.replace("Key.", "")
        for suffix in ['_l', '_r', '_gr']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        return name.capitalize()
    return str(key_str).upper()


def format_combo(combo_list):
    """格式化单一动作（如果是组合键则加方括号，单键则直接显示）"""
    if not combo_list:
        return ""
    formatted = [format_key_for_display(k) for k in combo_list]
    if len(formatted) > 1:
        return f"[{' + '.join(formatted)}]"
    else:
        return formatted[0]


def format_sequence(actions_list):
    """格式化整个动作序列，用箭头连接"""
    return " ➔ ".join(format_combo(combo) for combo in actions_list)


def is_modifier_name(name):
    """仅用于兼容旧版本JSON文件猜测辅助函数"""
    return any(m in name.lower() for m in ['ctrl', 'shift', 'alt', 'cmd', 'win'])


class KeyCaptureDialog:
    def __init__(self, parent, initial_actions=None, initial_delay=500, initial_name=""):
        self.top = tk.Toplevel(parent)
        self.top.title("录制按键")
        self.top.geometry("380x320")
        self.top.transient(parent)
        self.top.grab_set()

        # 核心数据结构升级：由单行列表升级为 动作组（列表嵌套列表）
        self.recorded_actions = initial_actions if initial_actions else []

        self.result = None
        self.listener = None
        self.is_recording = False

        self.current_pressed = set()  # 记录当前处于 KeyDown 状态的键
        self.current_combo = []      # 记录当前重叠在一起的组合序列

        # --- 状态提示区 ---
        self.status_var = tk.StringVar(value="等待操作...")
        tk.Label(self.top, textvariable=self.status_var,
                 font=("Arial", 10), fg="gray").pack(pady=5)

        self.key_display = tk.StringVar()
        self.update_key_display()
        tk.Label(self.top, textvariable=self.key_display, fg="blue", font=(
            "Arial", 12, "bold"), wraplength=350, justify="center").pack(pady=10)

        # --- 录制控制区 ---
        btn_record_frame = tk.Frame(self.top)
        btn_record_frame.pack(pady=5)
        self.btn_toggle_record = tk.Button(
            btn_record_frame, text="⏺ 开始录制 (将清空旧按键)", bg="lightpink", command=self.toggle_record)
        self.btn_toggle_record.pack()

        # --- 名称与时间设定区 ---
        frame_settings = tk.Frame(self.top)
        frame_settings.pack(pady=10)

        frame_name = tk.Frame(frame_settings)
        frame_name.pack(fill=tk.X, pady=2)
        tk.Label(frame_name, text="动作名称(可选):").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=initial_name)
        tk.Entry(frame_name, textvariable=self.name_var,
                 width=18).pack(side=tk.LEFT, padx=5)

        frame_delay = tk.Frame(frame_settings)
        frame_delay.pack(fill=tk.X, pady=2)
        tk.Label(frame_delay, text="动作间等待(ms):").pack(side=tk.LEFT)
        self.delay_var = tk.IntVar(value=int(initial_delay))
        self.entry_delay = tk.Entry(
            frame_delay, textvariable=self.delay_var, width=10)
        self.entry_delay.pack(side=tk.LEFT, padx=5)

        # --- 底部确认取消区 ---
        btn_frame = tk.Frame(self.top)
        btn_frame.pack(pady=10)
        self.btn_ok = tk.Button(btn_frame, text="确定",
                                command=self.on_ok, width=8)
        self.btn_ok.pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=self.on_cancel,
                  width=8).pack(side=tk.LEFT, padx=10)

        if not self.recorded_actions:
            self.status_var.set("请点击 [开始录制] 录入按键")

    def update_key_display(self):
        display_parts = []
        if self.recorded_actions:
            display_parts.append(format_sequence(self.recorded_actions))
        if self.current_combo:  # 实时显示正在按下的组合
            display_parts.append(format_combo(self.current_combo))

        if not display_parts:
            self.key_display.set("[ 无按键记录 ]")
        else:
            self.key_display.set(" ➔ ".join(display_parts))

    def _get_clean_key_char(self, key):
        try:
            if hasattr(key, 'char') and key.char is not None:
                if 1 <= ord(key.char) <= 26:
                    return chr(ord(key.char) + 96)
                return key.char
            return str(key).replace("'", "")
        except Exception:
            return str(key).replace("'", "")

    def toggle_record(self):
        if not self.is_recording:
            self.is_recording = True
            self.recorded_actions = []
            self.current_pressed.clear()
            self.current_combo.clear()
            self.update_key_display()
            self.btn_toggle_record.config(text="⏹ 停止录制", bg="lightblue")
            self.status_var.set("正在录制键盘输入中...")
            self.entry_delay.config(state=tk.DISABLED)
            self.btn_ok.config(state=tk.DISABLED)

            def on_press(key):
                key_char = self._get_clean_key_char(key)
                if key_char not in self.current_pressed:
                    self.current_pressed.add(key_char)
                    self.current_combo.append(key_char)  # 追加进当前的动作组合中
                    self.top.after(0, self.update_key_display)

            def on_release(key):
                key_char = self._get_clean_key_char(key)
                if key_char in self.current_pressed:
                    self.current_pressed.remove(key_char)
                    # 核心判定：只有当所有按下的键都松开时，才将这一组动作打包
                    if not self.current_pressed:
                        self.recorded_actions.append(list(self.current_combo))
                        self.current_combo.clear()
                        self.top.after(0, self.update_key_display)

            self.listener = keyboard.Listener(
                on_press=on_press, on_release=on_release)
            self.listener.start()
        else:
            self.is_recording = False
            if self.listener:
                self.listener.stop()
                self.listener = None

            # 如果强制点击停止录制时还有按键未松开，直接将其打包
            if self.current_combo:
                self.recorded_actions.append(list(self.current_combo))
                self.current_combo.clear()
                self.current_pressed.clear()
                self.update_key_display()

            self.btn_toggle_record.config(text="⏺ 重新录制", bg="lightpink")
            self.status_var.set("录制已停止，可修改等待时间与名称")
            self.entry_delay.config(state=tk.NORMAL)
            self.btn_ok.config(state=tk.NORMAL)

    def on_ok(self):
        if self.is_recording:
            self.toggle_record()

        try:
            delay = int(self.delay_var.get())
        except ValueError:
            messagebox.showerror("错误", "等待时间必须是整数！", parent=self.top)
            return

        self.result = {
            "name": self.name_var.get().strip(),
            # 这里输出的是干净清晰的动作组：[['ctrl', 'c'], ['enter']]
            "keys": self.recorded_actions,
            "delay": delay
        }
        self.top.destroy()

    def on_cancel(self):
        if self.listener:
            self.listener.stop()
        self.result = None
        self.top.destroy()


class MacroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python按键精灵")
        self.root.geometry("480x640")

        self.macro_data = []
        self.actions_to_execute = []
        self.controller = keyboard.Controller()

        self.is_running = threading.Event()
        self.is_paused = threading.Event()
        self.run_thread = None

        self.setup_ui()
        self.load_from_file(DEFAULT_FILE, silent=True)

    def setup_ui(self):
        frame_config = tk.LabelFrame(self.root, text="宏设定 (动作序列)")
        frame_config.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("action", "delay")
        self.tree = ttk.Treeview(
            frame_config, columns=columns, show="headings", height=8)
        self.tree.heading("action", text="动作/按键")
        self.tree.heading("delay", text="延时(ms)")
        self.tree.column("action", width=280)
        self.tree.column("delay", width=80, anchor=tk.CENTER)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tree.bind("<Double-1>", lambda e: self.edit_macro())

        scrollbar = ttk.Scrollbar(
            frame_config, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame_edit = tk.Frame(self.root)
        btn_frame_edit.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_frame_edit, text="➕ 添加",
                  command=self.add_macro).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame_edit, text="✏️ 修改",
                  command=self.edit_macro).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame_edit, text="➖ 删除",
                  command=self.delete_macro).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_frame_edit, text="⬆️ 上移",
                  command=self.move_up).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame_edit, text="⬇️ 下移",
                  command=self.move_down).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_frame_edit, text="🗑 清空", command=self.clear_macro).pack(
            side=tk.RIGHT, padx=2)

        frame_exec = tk.LabelFrame(self.root, text="执行控制 (仅执行列表中选定的行)")
        frame_exec.pack(fill=tk.X, padx=10, pady=5)

        frame_params = tk.Frame(frame_exec)
        frame_params.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(frame_params, text="执行次数(1-100):").grid(row=0,
                                                         column=0, padx=5, sticky="e")
        self.loop_var = tk.IntVar(value=1)
        tk.Spinbox(frame_params, from_=1, to=100, textvariable=self.loop_var,
                   width=8).grid(row=0, column=1, sticky="w")

        tk.Label(frame_params, text="执行间隔(ms):").grid(
            row=0, column=2, padx=5, sticky="e")
        self.interval_var = tk.IntVar(value=0)
        tk.Entry(frame_params, textvariable=self.interval_var,
                 width=10).grid(row=0, column=3, sticky="w")

        frame_btns = tk.Frame(frame_exec)
        frame_btns.pack(fill=tk.X, padx=10, pady=5)
        self.btn_start = tk.Button(
            frame_btns, text="▶ 开始执行", bg="lightgreen", command=self.start_macro)
        self.btn_start.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.btn_pause = tk.Button(
            frame_btns, text="⏸ 暂停", state=tk.DISABLED, command=self.pause_macro)
        self.btn_pause.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.btn_stop = tk.Button(
            frame_btns, text="⏹ 停止", state=tk.DISABLED, bg="pink", command=self.stop_macro)
        self.btn_stop.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        frame_file = tk.Frame(self.root)
        frame_file.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(frame_file, text="💾 保存到本地", command=self.save_dialog).pack(
            side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Button(frame_file, text="📂 从本地读取", command=self.load_dialog).pack(
            side=tk.LEFT, padx=5, expand=True, fill=tk.X)

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for act in self.macro_data:
            keys_str = format_sequence(act['keys'])
            display_name = act.get('name') if act.get('name') else keys_str
            self.tree.insert("", tk.END, values=(display_name, act['delay']))

    # --- 排序功能 ---
    def move_up(self):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        idx = self.tree.index(item)
        if idx > 0:
            self.macro_data[idx], self.macro_data[idx -
                                                  1] = self.macro_data[idx-1], self.macro_data[idx]
            self.refresh_tree()
            self.tree.selection_set(self.tree.get_children()[idx-1])

    def move_down(self):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[-1]
        idx = self.tree.index(item)
        if idx < len(self.macro_data) - 1:
            self.macro_data[idx], self.macro_data[idx +
                                                  1] = self.macro_data[idx+1], self.macro_data[idx]
            self.refresh_tree()
            self.tree.selection_set(self.tree.get_children()[idx+1])

    # --- 编辑功能 ---
    def add_macro(self):
        dialog = KeyCaptureDialog(self.root)
        self.root.wait_window(dialog.top)
        if dialog.result:
            self.macro_data.append(dialog.result)
            self.refresh_tree()

    def edit_macro(self):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        idx = self.tree.index(item)
        act = self.macro_data[idx]

        # 复制动作数据传入编辑器，防止直接修改了原引用
        actions_copy = [combo.copy() for combo in act['keys']]
        dialog = KeyCaptureDialog(self.root, initial_actions=actions_copy,
                                  initial_delay=act['delay'], initial_name=act.get('name', ''))
        self.root.wait_window(dialog.top)

        if dialog.result:
            self.macro_data[idx] = dialog.result
            self.refresh_tree()

    def delete_macro(self):
        selected = self.tree.selection()
        for item in reversed(selected):
            idx = self.tree.index(item)
            del self.macro_data[idx]
        self.refresh_tree()

    def clear_macro(self):
        if messagebox.askyesno("确认", "确定要清空所有设定的宏吗？"):
            self.macro_data.clear()
            self.refresh_tree()

    # --- 文件 IO ---
    def save_dialog(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=DEFAULT_FILE,
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filepath:
            try:
                try:
                    loop_count = self.loop_var.get()
                except tk.TclError:
                    loop_count = 1
                try:
                    interval_ms = self.interval_var.get()
                except tk.TclError:
                    interval_ms = 0

                save_list = []
                for act in self.macro_data:
                    act_dict = {"keys": act['keys'], "delay": act['delay']}
                    if act.get('name'):
                        act_dict['name'] = act['name']
                    save_list.append(act_dict)

                save_data = {
                    "loop_count": loop_count,
                    "interval_ms": interval_ms,
                    "macros": save_list
                }
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=4)
                messagebox.showinfo("成功", f"保存成功:\n{filepath}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败:\n{str(e)}")

    def load_dialog(self):
        filepath = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filepath:
            self.load_from_file(filepath)

    def load_from_file(self, filepath, silent=False):
        if not os.path.exists(filepath):
            if not silent:
                messagebox.showerror("错误", "文件不存在！")
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                self.macro_data = data
                self.loop_var.set(1)
                self.interval_var.set(0)
            elif isinstance(data, dict):
                self.macro_data = data.get("macros", [])
                self.loop_var.set(data.get("loop_count", 1))
                self.interval_var.set(data.get("interval_ms", 0))

            for act in self.macro_data:
                # 核心兼容逻辑：旧版本的 json 中 'keys' 是一维列表，需要转换为现在的二维嵌套动作组
                if act['keys'] and not isinstance(act['keys'][0], list):
                    new_actions = []
                    temp_combo = []
                    for k in act['keys']:
                        if is_modifier_name(str(k)):
                            temp_combo.append(k)
                        else:
                            new_actions.append(temp_combo + [k])
                            temp_combo = []
                    if temp_combo:
                        new_actions.append(temp_combo)
                    act['keys'] = new_actions

                delay_val = act.get('delay', 500)
                if isinstance(delay_val, float) and delay_val < 100:
                    act['delay'] = int(delay_val * 1000)
                else:
                    act['delay'] = int(delay_val)

            self.refresh_tree()
            if not silent:
                messagebox.showinfo("成功", "加载成功！")
        except Exception as e:
            if not silent:
                messagebox.showerror("错误", f"加载失败:\n{str(e)}")

    # --- 执行引擎 ---
    def _parse_key(self, key_str):
        if key_str.startswith("Key."):
            key_name = key_str.split(".")[1]
            return getattr(keyboard.Key, key_name, None)
        if len(key_str) == 1 and 1 <= ord(key_str) <= 26:
            return chr(ord(key_str) + 96)
        return key_str

    def _sleep_with_check(self, delay_sec):
        target_time = time.time() + delay_sec
        while time.time() < target_time:
            if not self.is_running.is_set():
                return False
            if self.is_paused.is_set():
                time.sleep(0.1)
                target_time += 0.1
                continue
            time.sleep(0.01)
        return True

    def _update_btn_start_ui(self, text, bg="lightgreen"):
        self.btn_start.config(text=text, bg=bg)

    def _enable_pause_btn(self):
        self.btn_pause.config(state=tk.NORMAL)

    def execute_macro_thread(self):
        self.is_running.set()

        try:
            for i in range(3, 0, -1):
                if not self.is_running.is_set():
                    return
                self.root.after(0, self._update_btn_start_ui,
                                f"准备切换... {i}s", "yellow")
                target_time = time.time() + 1.0
                while time.time() < target_time:
                    if not self.is_running.is_set():
                        return
                    time.sleep(0.05)

            self.root.after(0, self._enable_pause_btn)

            try:
                loops = max(1, min(100, self.loop_var.get()))
            except tk.TclError:
                loops = 1

            try:
                interval_sec = max(0, self.interval_var.get()) / 1000.0
            except tk.TclError:
                interval_sec = 0.0

            for i in range(loops):
                if not self.is_running.is_set():
                    break

                progress_text = f"运行中... ({i+1}/{loops})"
                self.root.after(0, self._update_btn_start_ui,
                                progress_text, "lightgray")

                for action in self.actions_to_execute:
                    if not self.is_running.is_set():
                        break
                    delay_sec = action['delay'] / 1000.0

                    # 全新极简执行逻辑：因为我们录制的就是真正的动作组 [['ctrl','c'], ['enter']]，所以执行也直接按组即可
                    for combo in action['keys']:
                        if not self.is_running.is_set():
                            break
                        while self.is_paused.is_set() and self.is_running.is_set():
                            time.sleep(0.1)

                        keys_to_press = [self._parse_key(
                            k) for k in combo if self._parse_key(k) is not None]

                        # 按下全部
                        for k in keys_to_press:
                            self.controller.press(k)
                        # 倒序松开
                        for k in reversed(keys_to_press):
                            self.controller.release(k)

                        if not self._sleep_with_check(delay_sec):
                            break

                if i < loops - 1 and self.is_running.is_set():
                    if not self._sleep_with_check(interval_sec):
                        break

        finally:
            self.root.after(0, self.reset_ui_state)

    def start_macro(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请先在列表中选中要执行的动作（支持多选）！")
            return

        self.actions_to_execute = [
            self.macro_data[self.tree.index(item)] for item in selected_items]

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        self.is_running.set()
        self.is_paused.clear()

        self.run_thread = threading.Thread(
            target=self.execute_macro_thread, daemon=True)
        self.run_thread.start()

    def pause_macro(self):
        if self.is_paused.is_set():
            self.is_paused.clear()
            self.btn_pause.config(text="⏸ 暂停")
        else:
            self.is_paused.set()
            self.btn_pause.config(text="▶ 继续")

    def stop_macro(self):
        self.is_running.clear()
        self.is_paused.clear()

    def reset_ui_state(self):
        self.btn_start.config(state=tk.NORMAL, text="▶ 开始执行", bg="lightgreen")
        self.btn_pause.config(state=tk.DISABLED, text="⏸ 暂停")
        self.btn_stop.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = MacroApp(root)
    root.mainloop()
