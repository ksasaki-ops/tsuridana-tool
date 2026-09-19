"""
tkinter メインウィンドウ
"""
import os
import subprocess
import sys
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from core.excel_writer import generate_excel
from core.image_generator import generate_jpg
from core.text_builder import OrderSpec
from utils.settings import load_settings, remember_tantou, save_settings


FILLER_OPTIONS = ["両側", "左のみ", "右のみ", "なし"]
TANA_COUNT_OPTIONS = ["1", "2", "3", "4"]
MATERIAL_OPTIONS = [
    "白ポリ",
    "ミディアムウォールナット",
    "ナチュラルメープル",
    "ダークウォールナット",
    "グレーオーク",
]


def _open_file(path: str):
    """生成ファイルをOSのデフォルトアプリで開く（Win / Mac / Linux 対応）"""
    try:
        if sys.platform == "darwin":          # macOS
            subprocess.Popen(["open", path])
        elif os.name == "nt":                  # Windows
            os.startfile(path)
        else:                                   # Linux 等
            subprocess.Popen(["xdg-open", path])
    except Exception:
        # 自動オープンに失敗してもファイル自体は保存済みなので無視
        pass


class MainWindow:
    def __init__(self, root: tk.Tk, settings_path: str | None = None):
        self.root = root
        self._settings_path = settings_path
        self._settings = load_settings(settings_path)
        root.title("洗濯機上吊戸棚 発注ツール")
        root.resizable(False, False)
        self._build_ui()

    # ──────────────────────────────────────────
    # UI 構築
    # ──────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        f = tk.Frame(self.root, padx=12, pady=12)
        f.pack()

        row = 0

        # タイトル
        tk.Label(f, text="洗濯機上吊戸棚 発注ツール", font=("MS Gothic", 14, "bold")).grid(
            row=row, column=0, columnspan=4, pady=(0, 8)
        )
        row += 1

        # ─── 担当者（選択を記憶・手入力で候補に追加） ───
        tk.Label(f, text="担当者").grid(row=row, column=0, sticky="e", **pad)
        self.var_tantou = tk.StringVar(value=self._settings["tantou"])
        self.combo_tantou = ttk.Combobox(f, textvariable=self.var_tantou,
                                         values=self._settings["tantou_list"], width=16)
        self.combo_tantou.grid(row=row, column=1, sticky="w", **pad)
        self.combo_tantou.bind("<<ComboboxSelected>>", lambda e: self._remember_tantou())
        self.combo_tantou.bind("<FocusOut>", lambda e: self._remember_tantou())
        row += 1

        # ─── お客様名 / 物件名 ───
        tk.Label(f, text="お客様名").grid(row=row, column=0, sticky="e", **pad)
        self.var_customer = tk.StringVar()
        tk.Entry(f, textvariable=self.var_customer, width=18).grid(row=row, column=1, sticky="w", **pad)

        tk.Label(f, text="物件名").grid(row=row, column=2, sticky="e", **pad)
        self.var_property = tk.StringVar()
        tk.Entry(f, textvariable=self.var_property, width=18).grid(row=row, column=3, sticky="w", **pad)
        row += 1

        # ─── 発注No / 発注日 ───
        tk.Label(f, text="発注No.").grid(row=row, column=0, sticky="e", **pad)
        self.var_hassou_no = tk.StringVar()
        tk.Entry(f, textvariable=self.var_hassou_no, width=18).grid(row=row, column=1, sticky="w", **pad)

        tk.Label(f, text="発注日").grid(row=row, column=2, sticky="e", **pad)
        self.var_hassou_date = tk.StringVar()
        tk.Entry(f, textvariable=self.var_hassou_date, width=12).grid(row=row, column=3, sticky="w", **pad)
        row += 1

        # ─── W / D / H ───
        for label, attr in [("W (mm)", "W"), ("D (mm)", "D"), ("H (mm)", "H")]:
            tk.Label(f, text=label).grid(row=row, column=0, sticky="e", **pad)
            var = tk.StringVar()
            setattr(self, f"var_{attr}", var)
            tk.Entry(f, textvariable=var, width=8).grid(row=row, column=1, sticky="w", **pad)
            row += 1

        # ─── 面材合わせ ───
        sep_row = row
        tk.Label(f, text="面材合わせ").grid(row=row, column=0, sticky="e", **pad)
        self.var_men_zai = tk.BooleanVar()
        tk.Radiobutton(f, text="あり", variable=self.var_men_zai, value=True, command=self._toggle_men_zai).grid(
            row=row, column=1, sticky="w"
        )
        tk.Radiobutton(f, text="なし", variable=self.var_men_zai, value=False, command=self._toggle_men_zai).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        tk.Label(f, text="扉品番").grid(row=row, column=0, sticky="e", **pad)
        self.var_tobira_hinban = tk.StringVar()
        self.entry_tobira_hinban = tk.Entry(f, textvariable=self.var_tobira_hinban, width=28)
        self.entry_tobira_hinban.grid(row=row, column=1, columnspan=3, sticky="w", **pad)
        row += 1

        # ─── 本体材質 ───
        tk.Label(f, text="本体材質").grid(row=row, column=0, sticky="e", **pad)
        self.var_material = tk.StringVar()
        ttk.Combobox(f, textvariable=self.var_material, values=MATERIAL_OPTIONS, width=22, state="readonly").grid(
            row=row, column=1, columnspan=3, sticky="w", **pad
        )
        row += 1

        # ─── 棚板枚数 ───
        tk.Label(f, text="棚板枚数").grid(row=row, column=0, sticky="e", **pad)
        self.var_tana_count = tk.StringVar()
        ttk.Combobox(f, textvariable=self.var_tana_count, values=TANA_COUNT_OPTIONS,
                     width=6, state="readonly").grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # ─── フィラー ───
        tk.Label(f, text="フィラー").grid(row=row, column=0, sticky="e", **pad)
        self.var_filler = tk.StringVar()
        filler_frame = tk.Frame(f)
        filler_frame.grid(row=row, column=1, columnspan=3, sticky="w")
        for opt in FILLER_OPTIONS:
            tk.Radiobutton(filler_frame, text=opt, variable=self.var_filler, value=opt).pack(side="left")
        row += 1

        # ─── HG ───
        tk.Label(f, text="ハンガーパイプ").grid(row=row, column=0, sticky="e", **pad)
        self.var_hg = tk.BooleanVar()
        tk.Radiobutton(f, text="あり", variable=self.var_hg, value=True).grid(row=row, column=1, sticky="w")
        tk.Radiobutton(f, text="なし", variable=self.var_hg, value=False).grid(row=row, column=2, sticky="w")
        row += 1

        # ─── 扉延長 ───
        tk.Label(f, text="扉延長").grid(row=row, column=0, sticky="e", **pad)
        self.var_tobira_enc = tk.BooleanVar()
        tk.Radiobutton(f, text="あり", variable=self.var_tobira_enc, value=True).grid(row=row, column=1, sticky="w")
        tk.Radiobutton(f, text="なし", variable=self.var_tobira_enc, value=False).grid(row=row, column=2, sticky="w")
        row += 1

        # ─── 切り欠き ───
        tk.Label(f, text="切り欠き").grid(row=row, column=0, sticky="e", **pad)
        self.var_kirikake = tk.BooleanVar()
        tk.Radiobutton(f, text="あり", variable=self.var_kirikake, value=True, command=self._toggle_kirikake).grid(
            row=row, column=1, sticky="w"
        )
        tk.Radiobutton(f, text="なし", variable=self.var_kirikake, value=False, command=self._toggle_kirikake).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        tk.Label(f, text="切り欠き W").grid(row=row, column=0, sticky="e", **pad)
        self.var_kk_W = tk.StringVar()
        self.entry_kk_W = tk.Entry(f, textvariable=self.var_kk_W, width=8)
        self.entry_kk_W.grid(row=row, column=1, sticky="w", **pad)
        tk.Label(f, text="H").grid(row=row, column=2, sticky="e", **pad)
        self.var_kk_H = tk.StringVar()
        self.entry_kk_H = tk.Entry(f, textvariable=self.var_kk_H, width=8)
        self.entry_kk_H.grid(row=row, column=3, sticky="w", **pad)
        row += 1

        # ─── 備考 ───
        tk.Label(f, text="備考").grid(row=row, column=0, sticky="e", **pad)
        self.var_bikou = tk.StringVar()
        tk.Entry(f, textvariable=self.var_bikou, width=40).grid(row=row, column=1, columnspan=3, sticky="w", **pad)
        row += 1

        # ─── 出力ボタン ───
        btn_frame = tk.Frame(f)
        btn_frame.grid(row=row, column=0, columnspan=4, pady=(10, 0))
        tk.Button(btn_frame, text="PNG出力", width=12, command=self._output_jpg).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Excel出力", width=12, command=self._output_excel).pack(side="left", padx=4)
        tk.Button(btn_frame, text="両方出力", width=12, command=self._output_both, bg="#4a90d9", fg="white").pack(
            side="left", padx=4
        )

        tk.Button(btn_frame, text="入力をクリア", width=12, command=self._on_clear).pack(side="left", padx=(16, 4))

        # 初期状態
        self._reset_fields()

    # ──────────────────────────────────────────
    # 入力クリア / 担当者の記憶
    # ──────────────────────────────────────────
    def _reset_fields(self):
        """全項目を初期状態に戻す（担当者は次の発注でも同じなので残す）"""
        for var in (self.var_customer, self.var_property, self.var_hassou_no,
                    self.var_W, self.var_D, self.var_H, self.var_tobira_hinban,
                    self.var_kk_W, self.var_kk_H, self.var_bikou):
            var.set("")
        self.var_hassou_date.set(date.today().strftime("%Y-%m-%d"))
        self.var_men_zai.set(True)
        self.var_material.set(MATERIAL_OPTIONS[0])
        self.var_tana_count.set("1")
        self.var_filler.set("両側")
        self.var_hg.set(True)
        self.var_tobira_enc.set(False)
        self.var_kirikake.set(False)
        self._toggle_men_zai()
        self._toggle_kirikake()

    def _on_clear(self):
        if messagebox.askyesno("入力をクリア", "入力内容をクリアして、次の発注を入力できる状態にしますか？（担当者はそのまま残ります）"):
            self._reset_fields()

    def _remember_tantou(self):
        """現在の担当者を保存し、次回起動時に復元できるようにする"""
        self._settings = remember_tantou(self._settings, self.var_tantou.get())
        self.combo_tantou["values"] = self._settings["tantou_list"]
        try:
            save_settings(self._settings, self._settings_path)
        except OSError:
            pass  # 保存できなくても発注書の出力は続けられる

    # ──────────────────────────────────────────
    # トグル処理
    # ──────────────────────────────────────────
    def _toggle_men_zai(self):
        state = "normal" if self.var_men_zai.get() else "disabled"
        self.entry_tobira_hinban.config(state=state)

    def _toggle_kirikake(self):
        state = "normal" if self.var_kirikake.get() else "disabled"
        self.entry_kk_W.config(state=state)
        self.entry_kk_H.config(state=state)

    # ──────────────────────────────────────────
    # フォーム値収集 & バリデーション
    # ──────────────────────────────────────────
    def _collect_spec(self) -> OrderSpec | None:
        errors = []

        customer = self.var_customer.get().strip().rstrip("様")
        if not customer:
            errors.append("お客様名を入力してください")

        def _int(var, label):
            v = var.get().strip()
            if not v:
                errors.append(f"{label} を入力してください")
                return 0
            try:
                return int(v)
            except ValueError:
                errors.append(f"{label} は整数で入力してください")
                return 0

        W = _int(self.var_W, "W")
        D = _int(self.var_D, "D")
        H = _int(self.var_H, "H")

        men_zai_ari = self.var_men_zai.get()
        tobira_hinban = " ".join(self.var_tobira_hinban.get().split())
        if men_zai_ari and not tobira_hinban:
            errors.append("面材合わせあり の場合、扉品番を入力してください")

        kirikake = self.var_kirikake.get()
        kk_W = kk_H = None
        if kirikake:
            kk_W = _int(self.var_kk_W, "切り欠きW")
            kk_H = _int(self.var_kk_H, "切り欠きH")

        if errors:
            messagebox.showerror("入力エラー", "\n".join(errors))
            return None

        self._remember_tantou()

        return OrderSpec(
            customer=customer,
            property_name=self.var_property.get().strip(),
            W=W,
            D=D,
            H=H,
            men_zai_ari=men_zai_ari,
            tobira_hinban=tobira_hinban,
            body_material=self.var_material.get(),
            filler=self.var_filler.get(),
            hg=self.var_hg.get(),
            tobira_enchou=self.var_tobira_enc.get(),
            kirikake=kirikake,
            kirikake_W=kk_W,
            kirikake_H=kk_H,
            hassou_no=self.var_hassou_no.get().strip(),
            hassou_date=self.var_hassou_date.get().strip(),
            bikou=" ".join(self.var_bikou.get().split()),
            tana_count=int(self.var_tana_count.get()),
            tantou=self.var_tantou.get().strip(),
        )

    # ──────────────────────────────────────────
    # 出力アクション
    # ──────────────────────────────────────────
    def _output_jpg(self):
        spec = self._collect_spec()
        if spec is None:
            return
        try:
            path = generate_jpg(spec)
            messagebox.showinfo("完了", f"PNGを保存しました:\n{path}")
            _open_file(path)
        except Exception as e:
            import traceback
            messagebox.showerror("エラー", traceback.format_exc())

    def _output_excel(self):
        spec = self._collect_spec()
        if spec is None:
            return
        try:
            path = generate_excel(spec)
            messagebox.showinfo("完了", f"Excelを保存しました:\n{path}")
            _open_file(path)
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def _output_both(self):
        spec = self._collect_spec()
        if spec is None:
            return
        msgs = []
        errors = []
        for fn, label in [(generate_jpg, "PNG"), (generate_excel, "Excel")]:
            try:
                path = fn(spec)
                msgs.append(f"{label}: {path}")
                _open_file(path)
            except Exception as e:
                errors.append(f"{label} エラー: {e}")

        if msgs:
            messagebox.showinfo("完了", "\n".join(msgs))
        if errors:
            messagebox.showerror("エラー", "\n".join(errors))
