import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import json
import os
import pandas as pd
import requests
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from binance.client import Client
# test comment  
# Optional candlestick plotting
try:
    import mplfinance as mpf
except ImportError:
    mpf = None

CONFIG_FILE = "trading_config.json"

class TradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Trading Terminal - USDT-M Futures")
        self.root.geometry("1600x900")
        # Status
        self.bot_status = tk.StringVar(value='Stopped')
        self.client = None

        # API & Telegram
        self.api_key = tk.StringVar()
        self.api_secret = tk.StringVar()
        self.telegram_token = tk.StringVar()
        self.telegram_chat_id = tk.StringVar()

        # Trading parameters
        self.trade_mode = tk.StringVar(value="Тестовая торговля")
        self.tp_pct = tk.DoubleVar(value=3.0)
        self.sl_pct = tk.DoubleVar(value=1.0)

        # Filters
        self.filter_volume = tk.StringVar(value="50M")
        self.filter_delta = tk.DoubleVar(value=4.0)
        self.filter_volatility = tk.DoubleVar(value=2.0)
        self.filter_trades = tk.StringVar(value="1M")
        self.filter_corr = tk.DoubleVar(value=70.0)
        self.filter_corr_enabled = tk.BooleanVar(value=False)

        # Timeframe
        self.timeframe = tk.StringVar(value="5m")

        # Data structures
        self.found_coins = []
        self.checkbox_vars = {}
        self.trading_coins = {}

        # Stats
        self.total_trades = tk.IntVar(value=0)
        self.profitable = tk.IntVar(value=0)
        self.losing = tk.IntVar(value=0)
        self.total_profit = tk.DoubleVar(value=0.0)
        self.total_profit_pct = tk.DoubleVar(value=0.0)
        self.online_trades = tk.IntVar(value=0)
        self.open_orders = tk.IntVar(value=0)
        self.online_volume = tk.DoubleVar(value=0.0)

        # Info panel
        self.info_vars = {
            "Volume24h": tk.StringVar(value="-"),
            "Change24h": tk.StringVar(value="-"),
            "Volatility": tk.StringVar(value="-"),
            "Trades24h": tk.StringVar(value="-"),
            "CorrBTC": tk.StringVar(value="-"),
        }
        self.current_symbol = None

        self.create_widgets()
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        # Top controls
        top = tk.Frame(self.root); top.pack(fill='x', pady=5)
        tk.Label(top, text="Status:").pack(side='left', padx=5)
        tk.Label(top, textvariable=self.bot_status).pack(side='left')
        tk.Button(top, text="Start", command=self.start_trading).pack(side='left', padx=5)
        tk.Button(top, text="Pause", command=self.pause_trading).pack(side='left', padx=5)
        tk.Button(top, text="Stop",  command=self.stop_trading).pack(side='left', padx=5)

        # API & Telegram
        api_frame = tk.LabelFrame(self.root, text="API & Telegram", padx=5, pady=5)
        api_frame.pack(fill='x', padx=5, pady=5)
        for lbl, var, hide in [
            ("Binance API Key:", self.api_key, False),
            ("Binance Secret Key:", self.api_secret, True),
            ("Telegram Token:", self.telegram_token, False),
            ("Telegram Chat ID:", self.telegram_chat_id, False)
        ]:
            row = tk.Frame(api_frame); row.pack(fill='x', pady=2)
            tk.Label(row, text=lbl, width=20, anchor='e').pack(side='left')
            tk.Entry(row, textvariable=var, show="*" if hide else "", width=40).pack(side='left')

        # Mode, TP/SL, TF
        mode = tk.Frame(self.root); mode.pack(fill='x', padx=5)
        tk.Label(mode, text="Mode:").pack(side='left', padx=5)
        ttk.Combobox(mode, textvariable=self.trade_mode,
                     values=["Тестовая торговля", "Реальная торговля"], width=20).pack(side='left')
        tk.Label(mode, text="TF:").pack(side='left', padx=5)
        ttk.Combobox(mode, textvariable=self.timeframe,
                     values=["1m", "5m", "15m", "1h", "4h", "1d"], width=6).pack(side='left')
        tk.Label(mode, text="TP %:").pack(side='left', padx=5)
        tk.Entry(mode, textvariable=self.tp_pct, width=6).pack(side='left')
        tk.Label(mode, text="SL %:").pack(side='left', padx=5)
        tk.Entry(mode, textvariable=self.sl_pct, width=6).pack(side='left')

        # Filters & Search
        filt = tk.LabelFrame(self.root, text="Filters & Search", padx=5, pady=5)
        filt.pack(fill='x', padx=5, pady=5)
        for text, var, w in [
            ("Vol $ (24h)", self.filter_volume, 8),
            ("Δ % (24h)", self.filter_delta, 6),
            ("Vol% (24h)", self.filter_volatility, 6),
            ("Trades (24h)", self.filter_trades, 8),
            ("Corr % (1h)", self.filter_corr, 6)
        ]:
            tk.Label(filt, text=text).pack(side='left', padx=5)
            tk.Entry(filt, textvariable=var, width=w).pack(side='left')
        tk.Checkbutton(filt, text="Use Corr", variable=self.filter_corr_enabled).pack(side='left', padx=5)
        tk.Button(filt, text="Search", command=self.refresh).pack(side='left', padx=10)

        # Found Coins list
        left = tk.LabelFrame(self.root, text="Found Coins", padx=5, pady=5)
        left.pack(side='left', fill='y', padx=5, pady=5)
        self.symbol_listbox = tk.Listbox(left, width=20, height=20)
        self.symbol_listbox.pack(fill='both', expand=True)
        self.symbol_listbox.bind('<<ListboxSelect>>', lambda e: self.on_symbol_select())

        # Selection checkboxes
        sel = tk.LabelFrame(self.root, text="Select for Trading", padx=5, pady=5)
        sel.pack(side='left', fill='y', padx=5, pady=5)
        self.sel_canvas = tk.Canvas(sel, width=150)
        self.sel_frame = tk.Frame(self.sel_canvas)
        vsb = tk.Scrollbar(sel, orient='vertical', command=self.sel_canvas.yview)
        self.sel_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self.sel_canvas.pack(side='left', fill='both', expand=True)
        self.sel_canvas.create_window((0,0), window=self.sel_frame, anchor='nw')
        self.sel_frame.bind("<Configure>", lambda e: self.sel_canvas.configure(scrollregion=self.sel_canvas.bbox("all")))

        # Summary
        summ = tk.LabelFrame(self.root, text="Результаты торговли", padx=5, pady=5)
        summ.pack(fill='x', padx=5)
        for txt, var in [
            ("Всего сделок:", self.total_trades),
            ("Прибыльных:", self.profitable),
            ("Убыточных:", self.losing),
            ("Профит $:", self.total_profit),
            ("(%)", self.total_profit_pct),
            ("Сейчас в онлайн:", self.online_trades),
            ("Орд. открытых:", self.open_orders),
            ("Сумма в сделках $:", self.online_volume)
        ]:
            tk.Label(summ, text=txt).pack(side='left', padx=5)
            tk.Label(summ, textvariable=var).pack(side='left')

        # Chart & Info
        chartf = tk.LabelFrame(self.root, text="Chart & Info", padx=5, pady=5)
        chartf.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        hdr = tk.Frame(chartf); hdr.pack(fill='x')
        tk.Label(hdr, text="Symbol:").pack(side='left')
        self.chart_symbol_label = tk.Label(hdr, text='-')
        self.chart_symbol_label.pack(side='left', padx=5)
        tk.Label(hdr, text="TF:").pack(side='left')
        cb_tf = ttk.Combobox(hdr, textvariable=self.timeframe,
                             values=["1m", "5m", "15m", "1h", "4h", "1d"], width=6)
        cb_tf.pack(side='left', padx=5)
        cb_tf.bind("<<ComboboxSelected>>", lambda e: self.plot_chart())
        infof = tk.Frame(chartf); infof.pack(fill='x', pady=5)
        for key, lab in [("Volume24h", "Vol24h:"), ("Change24h", "Δ24h:"), ("Volatility", "Vol%:"),
                         ("Trades24h", "Trades:"), ("CorrBTC", "Corr%:")]:
            tk.Label(infof, text=lab).pack(side='left', padx=5)
            tk.Label(infof, textvariable=self.info_vars[key]).pack(side='left')
        self.fig = plt.Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chartf)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

        # Bottom: Open Positions & Logs
        bottom = tk.Frame(self.root); bottom.pack(side='bottom', fill='both', expand=True, padx=5, pady=5)
        posf = tk.LabelFrame(bottom, text="Open Positions", padx=5, pady=5); posf.pack(fill='both', expand=True)
        self.pos_canvas = tk.Canvas(posf); self.pos_frame = tk.Frame(self.pos_canvas)
        vsb2 = tk.Scrollbar(posf, orient='vertical', command=self.pos_canvas.yview)
        self.pos_canvas.configure(yscrollcommand=vsb2.set); vsb2.pack(side='right', fill='y'); self.pos_canvas.pack(side='left', fill='both', expand=True)
        self.pos_canvas.create_window((0,0), window=self.pos_frame, anchor='nw')
        self.pos_frame.bind("<Configure>", lambda e: self.pos_canvas.configure(scrollregion=self.pos_canvas.bbox("all")))
        logf = tk.LabelFrame(bottom, text="Logs", padx=5, pady=5); logf.pack(fill='both', expand=True)
        self.log_text = scrolledtext.ScrolledText(logf, height=10); self.log_text.pack(fill='both', expand=True)
        for tag, color in [("info", "black"), ("success", "green"), ("error", "red")]:
            self.log_text.tag_configure(tag, foreground=color)

    def log(self, msg, tag="info"):
        self.log_text.insert(tk.END, msg + "\n", tag)
        self.log_text.see("end")

    def init_client(self):
        self.client = Client(self.api_key.get(), self.api_secret.get())
        self.log("✅ Connected to Binance Futures", "success")
        try:
            token = self.telegram_token.get(); cid = self.telegram_chat_id.get()
            requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={cid}&text=Bot+Started")
            self.log("✅ Telegram test sent", "success")
        except Exception as e:
            self.log(f"Telegram error: {e}", "error")

    def parse_kmb(self, s): return float(s.replace('K','e3').replace('M','e6').replace('B','e9'))
    def format_kmb_val(self, v):
        try: v=float(v)
        except: return str(v)
        if v>=1e9: return f"{v/1e9:.2f}B"
        if v>=1e6: return f"{v/1e6:.2f}M"
        if v>=1e3: return f"{v/1e3:.2f}K"
        return f"{v:.2f}"

    def refresh(self):
        if not getattr(self, 'running_search', False):
            threading.Thread(target=self.search_and_update, daemon=True).start()

def search_and_update(self):
    self.log("🔍 Поиск монет запущен...")  # ✅ Начало поиска
    self.running_search = True
    self.found_coins.clear()
    for w in self.sel_frame.winfo_children(): w.destroy()
    self.symbol_listbox.delete(0, 'end')

    try:
        if not self.client: self.init_client()
        tickers = self.client.futures_ticker()
        for t in tickers:
            sym = t['symbol']
            if not sym.endswith("USDT"): continue
            ch = abs(float(t['priceChangePercent']))
            vol = float(t['quoteVolume'])
            high = float(t['highPrice']); low = float(t['lowPrice']); op = float(t['openPrice'])
            volat = abs(high - low) / op * 100
            trades = int(t.get('count', 0))
            corr_ok = True
            if self.filter_corr_enabled.get():
                kl1 = self.client.futures_klines(symbol=sym, interval='1h', limit=50)
                kl2 = self.client.futures_klines(symbol="BTCUSDT", interval='1h', limit=50)
                df1 = pd.DataFrame(kl1, columns=["t","o","h","l","c","v",*range(6)])
                df2 = pd.DataFrame(kl2, columns=["t","o","h","l","c","v",*range(6)])
                corr_coef = df1['c'].astype(float).corr(df2['c'].astype(float)) * 100
                corr_ok = corr_coef <= float(self.filter_corr.get())
            if (ch >= self.filter_delta.get() and
                vol >= self.parse_kmb(self.filter_volume.get()) and
                volat >= self.filter_volatility.get() and
                trades >= self.parse_kmb(self.filter_trades.get()) and
                corr_ok):
                self.found_coins.append(sym)

        if not self.found_coins:
            self.log("⚠️ Монеты, соответствующие фильтрам, не найдены.", "info")
        else:
            for sym in self.found_coins:
                self.symbol_listbox.insert('end', sym)
                var = tk.BooleanVar(); self.checkbox_vars[sym] = var
                tk.Checkbutton(self.sel_frame, text=sym, variable=var).pack(anchor='w')

    except Exception as e:
        self.log(f"Search error: {e}", "error")

    finally:
        self.running_search = False
        self.log("✅ Поиск завершён.")  # ✅ Конец поиска

    def on_symbol_select(self):
        sel = self.symbol_listbox.curselection()
        if not sel: return
        sym = self.symbol_listbox.get(sel[0]); self.current_symbol = sym
        self.chart_symbol_label.config(text=sym)
        try:
            data = self.client.futures_ticker(symbol=sym)
            self.info_vars["Volume24h"].set(self.format_kmb_val(data["quoteVolume"]))
            self.info_vars["Change24h"].set(f"{float(data['priceChangePercent']):.2f}%")
            high, low, op = float(data["highPrice"]), float(data["lowPrice"]), float(data["openPrice"])
            self.info_vars["Volatility"].set(f"{abs(high-low)/op*100:.2f}%")
            self.info_vars["Trades24h"].set(self.format_kmb_val(data.get("count",0)))
            # correlation display (1h)
            kl1 = self.client.futures_klines(symbol=sym, interval='1h', limit=50)
            kl2 = self.client.futures_klines(symbol="BTCUSDT", interval='1h', limit=50)
            df1 = pd.DataFrame(kl1, columns=["t","o","h","l","c","v",*range(6)])
            df2 = pd.DataFrame(kl2, columns=["t","o","h","l","c","v",*range(6)])
            corr_val = df1['c'].astype(float).corr(df2['c'].astype(float)) * 100
            self.info_vars["CorrBTC"].set(f"{corr_val:.0f}%")
        except:
            self.info_vars["CorrBTC"].set("N/A")
            corr_percent = df1['c'].astype(float).corr(df2['c'].astype(float)) * 100
            self.info_vars["CorrBTC"].set(f"{corr_percent:.0f}%")
            self.plot_chart()  # ✅ Добавить эту строку
         

    def start_trading(self):
        self.bot_status.set('Running')
        self.trading_coins.clear()
        for sym, var in self.checkbox_vars.items():
            if var.get():
                self.trading_coins[sym] = {'status':'F','orders':[],'profit':0.0}
        for w in self.sel_frame.winfo_children(): w.config(state='disabled')
        self.update_positions_panel(); self.log("🛒 Started trading", "success")

    def pause_trading(self):
        self.bot_status.set('Paused')
        for w in self.sel_frame.winfo_children(): w.config(state='normal')
        self.log("⏸️ Paused trading", "info")

    def stop_trading(self):
        self.bot_status.set('Stopped')
        self.log("🛑 Bot stopped. Closing all positions...", "error")
        for sym in list(self.trading_coins.keys()): self.close_coin(sym)
        self.trading_coins.clear()
        for w in self.sel_frame.winfo_children(): w.config(state='normal')
        self.update_positions_panel()

    def update_positions_panel(self):
        self.online_trades.set(len(self.trading_coins))
        for w in self.pos_frame.winfo_children(): w.destroy()
        for sym, info in self.trading_coins.items():
            row = tk.Frame(self.pos_frame); row.pack(fill='x', pady=2)
            status = info.get('status','F')
            tk.Label(row, text=f"{sym} ({status})", width=15, anchor='w').pack(side='left')
            amt = sum(o.get('lot',0) for o in info.get('orders',[]))
            tk.Label(row, text=f"Amt:${amt:.2f}", width=12).pack(side='left')
            profit = info.get('profit',0.0) if status=='A' else 0.0
            tk.Label(row, text=f"Profit:${profit:.2f}", width=12).pack(side='left')
            tk.Button(row, text="Close", command=lambda s=sym: self.close_coin(s)).pack(side='right')

    def close_coin(self, sym):
        if sym in self.trading_coins:
            del self.trading_coins[sym]
            self.update_positions_panel()
            self.log(f"Closed {sym}", "info")

    def plot_chart(self):
        if not self.current_symbol: return
        try:
            klines = self.client.futures_klines(symbol=self.current_symbol, interval=self.timeframe.get(), limit=100)
            df = pd.DataFrame(klines, columns=['t','o','h','l','c','v',*range(6)])
            df['t'] = pd.to_datetime(df['t'], unit='ms'); df.set_index('t', inplace=True); df=df.astype(float)
            self.ax.clear()
            if mpf:
                mpf.plot(df, type='candle', ax=self.ax, style='charles', volume=False)
            else:
                self.ax.plot(df.index, df['c'])
            # plot orders
            if self.current_symbol in self.trading_coins:
                for o in self.trading_coins[self.current_symbol]['orders']:
                    m = '^' if o.get('type') in ['AOB','LM'] else 'v'
                    self.ax.scatter(df.index[-1], o.get('price'), marker=m)
            self.canvas.draw()
            self.root.after(5000, self.plot_chart)
        except Exception as e:
            self.log(f"Chart error: {e}", "error")

    def save_config(self):
        cfg = {
            'api_key': self.api_key.get(), 'api_secret': self.api_secret.get(),
            'telegram_token': self.telegram_token.get(), 'telegram_chat_id': self.telegram_chat_id.get(),
            'trade_mode': self.trade_mode.get(), 'tp_pct': self.tp_pct.get(), 'sl_pct': self.sl_pct.get(),
            'filter_volume': self.filter_volume.get(), 'filter_delta': self.filter_delta.get(),
            'filter_volatility': self.filter_volatility.get(), 'filter_trades': self.filter_trades.get(),
            'filter_corr': self.filter_corr.get(), 'filter_corr_enabled': self.filter_corr_enabled.get(),
            'timeframe': self.timeframe.get()
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.api_key.set(cfg.get('api_key','')); self.api_secret.set(cfg.get('api_secret',''))
                self.telegram_token.set(cfg.get('telegram_token','')); self.telegram_chat_id.set(cfg.get('telegram_chat_id',''))
                self.trade_mode.set(cfg.get('trade_mode','Тестовая торговля'))
                self.tp_pct.set(cfg.get('tp_pct',3.0)); self.sl_pct.set(cfg.get('sl_pct',1.0))
                self.filter_volume.set(cfg.get('filter_volume','50M'))
                self.filter_delta.set(cfg.get('filter_delta',4.0))
                self.filter_volatility.set(cfg.get('filter_volatility',2.0))
                self.filter_trades.set(cfg.get('filter_trades','1M'))
                self.filter_corr.set(cfg.get('filter_corr',70.0))
                self.filter_corr_enabled.set(cfg.get('filter_corr_enabled',False))
                self.timeframe.set(cfg.get('timeframe','5m'))
            except Exception as e:
                self.log(f"Config load error: {e}", "error")

    def on_close(self):
        self.save_config()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TradingApp(root)
    root.mainloop()


