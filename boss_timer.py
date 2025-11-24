import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta
import json
import threading
import time
import os

CONFIG_FILE = "boss_timers.json"

class BossTimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Boss 刷新倒计时")
        self.root.geometry("680x550")
        self.root.resizable(True, True)

        self.bosses = []
        self.load_config()

        self.create_widgets()

        self.running = True
        self.update_thread = threading.Thread(target=self.update_countdowns, daemon=True)
        self.update_thread.start()

        self.sort_bosses()
        self.refresh_tree()

    def create_widgets(self):
        # ========== 顶部工具栏 ==========
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=5, fill=tk.X, padx=10)

        # 全选按钮
        self.select_all_btn = tk.Button(top_frame, text="全选", command=self.toggle_select_all)
        self.select_all_btn.pack(side=tk.LEFT, padx=(0, 5))

        # 开始计时（对选中项）
        tk.Button(top_frame, text="开始计时",
                  command=self.start_selected).pack(side=tk.LEFT, padx=(0, 5))

        # 重置计时（同“开始计时”，语义重复但按需求保留）
        tk.Button(top_frame, text="重置计时",
                  command=self.reset_selected).pack(side=tk.LEFT, padx=(0, 5))

        # 删除选中
        tk.Button(top_frame, text="删除选中",
                  command=self.delete_selected).pack(side=tk.LEFT, padx=(0, 20))

        # 添加 Boss（靠右）
        tk.Button(top_frame, text="添加 Boss", command=self.add_boss).pack(side=tk.RIGHT)

        # ========== 树形表格 ==========
        columns = ("select", "map", "level", "refresh_time", "countdown", "edit")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=18)
        
        self.tree.heading("select", text="")
        self.tree.heading("map", text="地图名称")
        self.tree.heading("level", text="Boss等级")
        self.tree.heading("refresh_time", text="刷新间隔 (时:分:秒)")
        self.tree.heading("countdown", text="倒计时")
        self.tree.heading("edit", text="操作")  # ← 新增操作列标题

        self.tree.column("select", width=30, anchor="center")
        self.tree.column("map", width=100)
        self.tree.column("level", width=80, anchor="center")
        self.tree.column("refresh_time", width=120, anchor="center")
        self.tree.column("countdown", width=120, anchor="center")
        self.tree.column("edit", width=60, anchor="center")  # ← 编辑列宽度

        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 绑定点击事件
        self.tree.bind("<Button-1>", self.on_header_click)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        # ========== 底部状态栏（可选）==========
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.status_label = tk.Label(status_frame, text="就绪", fg="gray")
        self.status_label.pack(side=tk.LEFT)

    # ====== 核心方法 ======
    def on_header_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading":
            col = self.tree.identify_column(event.x)
            if col == "#1":
                self.toggle_select_all()
                return "break"

    def on_tree_click(self, event):
        """统一处理 Treeview 点击事件"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        # 获取行索引
        row_index = self.tree.index(row_id)

        if col == "#1":  # 选择列
            if row_index < len(self.bosses):
                boss = self.bosses[row_index]
                boss["selected"] = not boss.get("selected", False)
                mark = "✅" if boss["selected"] else "⬜"
                self.tree.set(row_id, "select", mark)

        elif col == "#6":  # 编辑列（第6列）
            self.edit_boss(row_index)

    def edit_boss(self, index):
        """编辑指定索引的 Boss"""
        if index >= len(self.bosses):
            return
        boss = self.bosses[index]

        # 创建临时窗口用于输入
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑 Boss")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()  # 模态窗口

        tk.Label(dialog, text="地图名称:").pack(pady=(10, 0))
        map_entry = tk.Entry(dialog)
        map_entry.pack()
        map_entry.insert(0, boss["map"])

        tk.Label(dialog, text="Boss等级:").pack()
        level_entry = tk.Entry(dialog)
        level_entry.pack()
        level_entry.insert(0, boss["level"])

        tk.Label(dialog, text="刷新间隔 (H:M:S):").pack()
        time_entry = tk.Entry(dialog)
        time_entry.pack()
        time_entry.insert(0, boss["refresh_interval"])

        def save_and_close():
            new_map = map_entry.get().strip()
            new_level = level_entry.get().strip()
            new_time = time_entry.get().strip()

            if not new_map or not new_level or not new_time:
                messagebox.showwarning("警告", "所有字段不能为空！", parent=dialog)
                return

            try:
                self.parse_time_str(new_time)
            except ValueError as e:
                messagebox.showerror("错误", str(e), parent=dialog)
                return

            # 更新数据
            boss["map"] = new_map
            boss["level"] = new_level
            boss["refresh_interval"] = new_time

            # 如果已有下次刷新时间，则重新计算（保持相对时间）
            if boss["next_refresh"]:
                interval = self.parse_time_str(new_time)
                boss["next_refresh"] = datetime.now() + interval

            self.sort_bosses()
            self.refresh_tree()
            dialog.destroy()

        tk.Button(dialog, text="保存", command=save_and_close, bg="#4CAF50", fg="white").pack(pady=10)
        dialog.bind('<Return>', lambda e: save_and_close())  # 回车保存

    def on_cell_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if col == "#1":
            idx = self.tree.index(row)
            if idx < len(self.bosses):
                boss = self.bosses[idx]
                boss["selected"] = not boss.get("selected", False)
                mark = "✅" if boss["selected"] else "⬜"
                self.tree.set(row, "select", mark)
            return "break"

    def toggle_select_all(self):
        self.all_selected = not getattr(self, 'all_selected', False)
        for boss in self.bosses:
            boss["selected"] = self.all_selected
        self.refresh_tree()
        self.select_all_btn.config(text="取消全选" if self.all_selected else "全选")

    def add_boss(self):
        map_name = simpledialog.askstring("添加 Boss", "地图名称:")
        if not map_name: return
        level = simpledialog.askstring("添加 Boss", "Boss等级:")
        if not level: return
        refresh = simpledialog.askstring("添加 Boss", "刷新间隔 (例如: 1:30:00):", initialvalue="00:00:00")
        if not refresh: return
        try:
            self.parse_time_str(refresh)
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return

        self.bosses.append({
            "map": map_name,
            "level": level,
            "refresh_interval": refresh,
            "next_refresh": None,
            "selected": False
        })
        self.refresh_tree()

    def get_selected_indices(self):
        return [i for i, boss in enumerate(self.bosses) if boss.get("selected", False)]

    def start_selected(self):
        """开始计时：为选中的 Boss 设置下次刷新时间"""
        selected = self.get_selected_indices()
        
        if not selected:
            self.status_label.config(text="⚠️ 请先选择要开始计时的 Boss")
            return
        try:
            for i in selected:
                interval = self.parse_time_str(self.bosses[i]["refresh_interval"])
                self.bosses[i]["next_refresh"] = datetime.now() + interval
                self.bosses[i]["selected"] = False
            self.sort_bosses()
            self.refresh_tree()
            self.status_label.config(text=f"✅ 已为 {len(selected)} 个 Boss 开始计时")
        except Exception as e:
            messagebox.showerror("错误", f"开始计时失败: {e}")

    def reset_selected(self):
        """重置计时：功能与 start_selected 完全相同"""
        self.start_selected()  # 复用逻辑

    def delete_selected(self):
        selected = self.get_selected_indices()
        if not selected:
            self.status_label.config(text="⚠️ 请先选择要删除的 Boss")
            return
        if messagebox.askyesno("确认删除", f"确定删除 {len(selected)} 个选中的 Boss？"):
            for i in reversed(selected):
                del self.bosses[i]
            self.refresh_tree()
            self.status_label.config(text=f"🗑️ 已删除 {len(selected)} 个 Boss")

    # ====== 工具方法 ======
    def parse_time_str(self, time_str):
        try:
            parts = list(map(int, time_str.split(':')))
            if len(parts) == 3:
                h, m, s = parts
            elif len(parts) == 2:
                h, m, s = 0, parts[0], parts[1]
            elif len(parts) == 1:
                h, m, s = 0, 0, parts[0]
            else:
                raise ValueError
            return timedelta(hours=h, minutes=m, seconds=s)
        except:
            raise ValueError("时间格式错误，请输入 H:M:S、M:S 或 S")

    def format_timedelta(self, td):
        total_seconds = int(td.total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def sort_bosses(self):
        def get_sort_key(boss):
            if boss["next_refresh"] is None:
                return float('inf')
            remaining = (boss["next_refresh"] - datetime.now()).total_seconds()
            return max(remaining, 0)
        self.bosses.sort(key=get_sort_key)

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for boss in self.bosses:
            select_mark = "✅" if boss.get("selected", False) else "⬜"
            countdown_str = "--:--:--"
            if boss["next_refresh"]:
                remaining = boss["next_refresh"] - datetime.now()
                if remaining.total_seconds() > 0:
                    countdown_str = self.format_timedelta(remaining)
                else:
                    countdown_str = "0:00:00"
            self.tree.insert("", "end", values=(
                select_mark,
                boss["map"],
                boss["level"],
                boss["refresh_interval"],
                countdown_str,
                "✎ 编辑"  # ← 新增编辑文本
            ))

    def update_countdowns(self):
        while self.running:
            time.sleep(1)
            if int(time.time()) % 5 == 0:
                self.root.after(0, self.sort_and_refresh)

    def sort_and_refresh(self):
        self.sort_bosses()
        self.refresh_tree()

    def save_config(self):
        try:
            save_data = []
            for b in self.bosses:
                save_data.append({
                    "map": b["map"],
                    "level": b["level"],
                    "refresh_interval": b["refresh_interval"]
                })
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            self.status_label.config(text="💾 配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.bosses = []
                for item in data:
                    self.bosses.append({
                        "map": item["map"],
                        "level": item["level"],
                        "refresh_interval": item["refresh_interval"],
                        "next_refresh": None,
                        "selected": False
                    })
            except Exception as e:
                messagebox.showerror("警告", f"加载配置失败: {e}")
                self.bosses = []

    def reload_and_sort(self):
        """供菜单调用：重新加载并排序"""
        self.load_config()
        self.sort_bosses()
        self.refresh_tree()
        self.status_label.config(text="🔄 配置已重新加载")

    def on_closing(self):
        self.running = False
        self.save_config()
        self.root.destroy()


# ====== 菜单栏 ======
def add_menu(root, app):
    menubar = tk.Menu(root)
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="保存", command=app.save_config, accelerator="Ctrl+S")
    file_menu.add_command(label="重新加载", command=app.reload_and_sort)
    file_menu.add_separator()
    file_menu.add_command(label="退出", command=root.quit)
    menubar.add_cascade(label="文件", menu=file_menu)
    root.config(menu=menubar)

    # 绑定快捷键
    root.bind('<Control-s>', lambda e: app.save_config())


# ====== 启动 ======
if __name__ == "__main__":
    root = tk.Tk()
    app = BossTimerApp(root)
    add_menu(root, app)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()