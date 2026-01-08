import customtkinter as ctk
import yt_dlp
import threading
import os
import sys
import traceback
from tkinter import messagebox, filedialog

# --- 基础路径逻辑 ---
def get_base_path():
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.abspath(".")
    except:
        return "."

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- 输入行组件 ---
class URLInputRow(ctk.CTkFrame):
    def __init__(self, master, app_instance, is_adder=True):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.base_dir = self.app.base_dir
        self.is_running = False
        
        self.grid_columnconfigure(0, weight=1)
        
        # 1. 输入框
        self.url_entry = ctk.CTkEntry(self, placeholder_text="在此粘贴视频链接...", height=40)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        # 2. 按钮
        self.btn_action = None
        if is_adder:
            self.show_add_button()
        else:
            self.show_delete_button()

        # 3. 进度条
        self.progress_bar = ctk.CTkProgressBar(self, height=4)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 5))
        self.progress_bar.grid_remove()
        self.progress_bar.set(0)
        
        # 4. 状态文字
        self.status_label = ctk.CTkLabel(self, text="", font=("Arial", 10), text_color="gray", anchor="w")
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=5)

    def show_add_button(self):
        if self.btn_action: self.btn_action.destroy()
        self.btn_action = ctk.CTkButton(
            self, text="➕", width=40, height=40, 
            fg_color="#1F6AA5", hover_color="#144870",
            command=self.app.on_add_click
        )
        self.btn_action.grid(row=0, column=1)

    def show_delete_button(self):
        if self.btn_action: self.btn_action.destroy()
        self.btn_action = ctk.CTkButton(
            self, text="×", width=40, height=40, 
            fg_color="#D32F2F", hover_color="#B71C1C",
            command=self.delete_self
        )
        self.btn_action.grid(row=0, column=1)

    def transform_to_normal_row(self):
        self.show_delete_button()

    def delete_self(self):
        if self in self.app.input_rows:
            self.app.input_rows.remove(self)
        self.destroy()

    def start_download(self):
        link = self.url_entry.get().strip()
        if not link or self.is_running: return
        
        self.is_running = True
        self.progress_bar.set(0) 
        self.progress_bar.grid()
        self.url_entry.configure(state="disabled")
        
        self.status_label.configure(text="正在智能解析...", text_color="#E59400")
        threading.Thread(target=self.run_logic, args=(link,)).start()

    def run_logic(self, link, referer=None):
        try:
            save_path = self.app.save_path
            mode = self.app.format_var.get()
            
            opts = {
                'outtmpl': f'{save_path}/%(title)s.%(ext)s',
                'quiet': True, 'no_warnings': True,
                'writethumbnail': True, 'addmetadata': True,
                'ffmpeg_location': self.base_dir,
                'progress_hooks': [self.progress_hook]
            }

            cookie_file = os.path.join(self.base_dir, "cookies.txt")
            if os.path.exists(cookie_file): opts['cookiefile'] = cookie_file
            if referer: opts['http_headers'] = {'Referer': referer}

            # === 智能逻辑核心：后台自动兼容 PR/AE ===
            # 我们通过添加 ffmpeg 参数，强制输出为 H.264 编码
            
            common_ffmpeg_args = {
                # 强制视频编码为 libx264 (H.264)，音频为 aac
                # -preset superfast: 牺牲一点点压缩率，换取极快的转码速度 (否则4K转码太慢)
                # -crf 20: 保证高质量
                'ffmpeg': ['-c:v', 'libx264', '-preset', 'superfast', '-crf', '20', '-c:a', 'aac']
            }

            if "720P" in mode:
                opts.update({'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]', 'merge_output_format': 'mp4'})
                # 720P 通常本身就是 H264，但为了保险也可以加上参数，或者信赖默认
            
            elif "1080P" in mode:
                opts.update({'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 'merge_output_format': 'mp4'})
            
            elif "最高画质" in mode:
                # 【核心修改】
                # 下载最高画质，并且在下载后执行 'postprocessor_args' 进行隐形转码
                opts.update({
                    'format': 'bestvideo+bestaudio/best',
                    'merge_output_format': 'mp4',
                    'postprocessor_args': common_ffmpeg_args # <--- 这一行让它变成全兼容格式
                })
            
            elif "纯音频" in mode:
                opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})

            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([link])
            self.after(0, lambda: self.finish(True))

        except Exception as e:
            err_msg = str(e)
            if "HTTP Error 403" in err_msg or "Forbidden" in err_msg:
                self.after(0, lambda: self.ask_referer(link))
            else:
                self.after(0, lambda: self.finish(False, f"错误: {err_msg[:20]}..."))

    def ask_referer(self, link):
        if not self.winfo_exists(): return
        user_input = ctk.CTkInputDialog(text=f"需要防盗链验证。\n请粘贴来源网页地址：", title="Vimeo 助手").get_input()
        if user_input:
            self.status_label.configure(text="重试中...", text_color="#E59400")
            threading.Thread(target=self.run_logic, args=(link, user_input)).start()
        else:
            self.finish(False, "已取消")

    def progress_hook(self, d):
        if not self.winfo_exists(): return
        if d['status'] == 'downloading':
            try: 
                p = float(d['_percent_str'].strip('%')) / 100
                self.progress_bar.set(p)
                self.status_label.configure(text=f"{d['_percent_str']} | {d['_speed_str']}")
            except: pass
        elif d['status'] == 'finished':
            self.progress_bar.set(1)
            # 在这里给用户反馈，说明正在进行后台处理
            self.status_label.configure(text="正在转码 (适配PR/AE)...", text_color="#00E5FF")

    def finish(self, success, msg=""):
        if not self.winfo_exists(): return
        if success:
            self.status_label.configure(text="✅ 完成", text_color="#00FF00")
            self.url_entry.configure(state="normal")
            self.is_running = False 
        else:
            self.status_label.configure(text=msg, text_color="red")
            self.url_entry.configure(state="normal")
            self.is_running = False


# --- 主程序 ---
class FinalDownloader(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.base_dir = get_base_path()
        self.input_rows = [] 
        self.title("全能下载器 Pro")
        self.geometry("700x650")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.save_path = os.path.join(os.path.expanduser("~"), "Downloads")

        # 1. 标题
        self.lbl_title = ctk.CTkLabel(self, text="全能媒体流下载", font=("微软雅黑", 22, "bold"))
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(25, 5))
        self.lbl_sub = ctk.CTkLabel(self, text="支持 YouTube / Bilibili / 新片场 / Vimeo", text_color="gray")
        self.lbl_sub.grid(row=1, column=0, padx=20, pady=(0, 20))

        # 2. 链接输入区
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text=None, fg_color="transparent")
        self.scroll_frame.grid(row=2, column=0, padx=20, pady=0, sticky="nsew")

        # 3. 底部操作区
        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.grid(row=3, column=0, padx=20, pady=20, sticky="ew")

        # [设置行]
        self.settings_row = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        self.settings_row.pack(fill="x", padx=15, pady=(15, 10))
        
        self.path_btn = ctk.CTkButton(self.settings_row, text="📂 更改目录", width=90, fg_color="gray", command=self.select_folder)
        self.path_btn.pack(side="left")
        self.open_btn = ctk.CTkButton(self.settings_row, text="下载打开", width=80, fg_color="#444", hover_color="#666", command=self.open_save_folder)
        self.open_btn.pack(side="left", padx=5)
        self.path_label = ctk.CTkLabel(self.settings_row, text=f"{self.save_path[-20:]}", text_color="#CCC", font=("Arial", 11))
        self.path_label.pack(side="left", padx=5)

        # --- 右侧：画质控制 (回归清爽) ---
        self.format_var = ctk.StringVar(value="最高画质 (4K/8K)") 
        self.format_option = ctk.CTkOptionMenu(
            self.settings_row, width=160, variable=self.format_var,
            values=[
                "720P 快速模式", 
                "1080P 均衡模式", 
                "最高画质 (4K/8K)", # 内置了智能转码逻辑
                "纯音频提取 (MP3)"
            ]
        )
        self.format_option.pack(side="right")

        self.divider = ctk.CTkFrame(self.bottom_frame, height=2, fg_color="#333")
        self.divider.pack(fill="x", padx=15, pady=5)

        self.btn_start = ctk.CTkButton(
            self.bottom_frame, 
            text="🚀 开始全部下载", 
            command=self.start_all, 
            height=55, 
            font=("微软雅黑", 18, "bold"),
            fg_color="#00C853", 
            hover_color="#009624"
        )
        self.btn_start.pack(fill="x", padx=15, pady=(10, 15))
        
        self.check_env()
        self.create_row(is_adder=True)

    def check_env(self):
        txt = ""
        if os.path.exists(os.path.join(self.base_dir, "cookies.txt")): txt = "✅VIP身份激活 "
        else: txt = "ℹ️游客模式 "
        if not os.path.exists(os.path.join(self.base_dir, "ffmpeg.exe")): txt += "| ❌缺FFmpeg"
        ctk.CTkLabel(self, text=txt, text_color="gray", font=("Arial", 10)).grid(row=4, column=0, pady=(0, 5))

    def on_add_click(self):
        if self.input_rows:
            self.input_rows[-1].transform_to_normal_row()
        self.create_row(is_adder=True)

    def create_row(self, is_adder=True):
        row = URLInputRow(self.scroll_frame, self, is_adder=is_adder)
        row.pack(fill="x", pady=5)
        self.input_rows.append(row)
        self.after(100, lambda: self._scroll_bottom())

    def _scroll_bottom(self):
        try: self.scroll_frame._parent_canvas.yview_moveto(1.0)
        except: pass

    def start_all(self):
        active_cnt = 0
        for row in self.input_rows:
            link = row.url_entry.get().strip()
            if link and not row.is_running:
                row.start_download()
                active_cnt += 1
        
        if active_cnt == 0:
            has_running = any(row.is_running for row in self.input_rows)
            if not has_running:
                messagebox.showinfo("提示", "请先粘贴视频链接！")

    def select_folder(self):
        d = filedialog.askdirectory()
        if d: 
            self.save_path = d
            self.path_label.configure(text=f"{d[-20:]}")

    def open_save_folder(self):
        try:
            os.startfile(self.save_path)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {e}")

if __name__ == "__main__":
    try:
        app = FinalDownloader()
        app.mainloop()
    except Exception:
        import tkinter
        import tkinter.messagebox
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showerror("程序崩溃", traceback.format_exc())