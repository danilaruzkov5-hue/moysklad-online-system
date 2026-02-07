import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime
import io
from sqlalchemy import create_engine, text

# --- НАСТРОЙКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# --- БАЗА ДАННЫХ ---
DB_URL = st.secrets.get("DB_URL", "sqlite:///warehouse.db")
engine = create_engine(DB_URL)

def init_db():
    with engine.connect() as conn:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS stock 
            (uuid TEXT PRIMARY KEY, name TEXT, article TEXT, barcode TEXT, quantity REAL, box_num TEXT, type TEXT)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS archive 
            (uuid TEXT PRIMARY KEY, name TEXT, article TEXT, barcode TEXT, quantity REAL, box_num TEXT, type TEXT, ship_date TEXT)'''))
        conn.commit()

init_db()

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

def reset_selection():
    st.session_state.reset_counter += 1

st.set_page_config(layout="wide", page_title="Складской Терминал")

def load_api_data():
    url = f"https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000&filter=store=https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}"
    try:
        res = requests.get(url, headers=HEADERS)
        return res.json().get('rows', []) if res.status_code == 200 else []
    except: return []

ms_rows = load_api_data()
api_status = "🟢 Связь с МойСклад: Установлена" if ms_rows else "🔴 Связь с МойСклад: Ошибка"

st.title("📦 Единая база склада (ИП / ООО)")
st.caption(api_status)

# --- ПРИЕМКА ТОВАРА ---
with st.sidebar:
    st.header("📥 Приемка")
    uploaded_file = st.file_uploader("Загрузи Excel (Баркод, Кол-во, Короб)", type=["xlsx"])
    target_type = st.radio("Тип поставки:", ["ИП", "ООО"])

    if uploaded_file and st.button("➕ Добавить на баланс"):
        try:
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"]
            mapping = {str(r.get('code')): (r.get('article', '-'), r.get('name', 'Неизвестно')) for r in ms_rows}
            with engine.connect() as conn:
                for _, row in new_data.iterrows():
                    art, name = mapping.get(str(row["Баркод"]), ("-", "Новый товар"))
                    uid = f"ID_{datetime.now().timestamp()}_{_}"
                    conn.execute(text("INSERT INTO stock VALUES (:u, :n, :a, :b, :q, :bn, :t)"),
                                {"u":str(uid), "n":str(name), "a":str(art), "b":str(row["Баркод"]), 
                                 "q":float(row["Кол-во"]), "bn":str(row["Номер короба"]), "t":str(target_type)})
                conn.commit()
            reset_selection()
            st.success("Данные сохранены!")
            st.rerun()
        except Exception as e: st.error(f"Ошибка: {e}")

search = st.text_input("🔍 Быстрый поиск (Баркод / Артикул / Короб)")
t1, t2, t3, t4, t5 = st.tabs(["🏠 ИП", "🏢 ООО", "📜 Архив", "💰 Хранение", "📊 Итого"])

def render_table(storage_type, key):
    df = pd.read_sql(text(f"SELECT * FROM stock WHERE type='{storage_type}'"), engine)
    if search:
        df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
    
    if not df.empty:
        table_key = f"table_{key}_{st.session_state.reset_counter}"
        sel = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=table_key)
        idx = sel.get("selection", {}).get("rows", [])
        
        if idx:
            c1, c2 = st.columns(2)
            selected_rows = df.iloc[idx].copy()
            
            # Подготовка файла поставки (Требование Дмитрия)
out = io.BytesIO()
            exp_df = selected_rows[['barcode', 'quantity', 'box_num']].copy()
            exp_df.columns = ["Баркод", "Кол-во", "Номер короба"]
            for col in ["Дата забора", "Склад", "Юр. лицо", "ФИО сотрудника"]:
                exp_df[col] = "" # Шапки для ручного ввода
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                exp_df.to_excel(writer, index=False)
            
            # Кнопка Завершить (сразу отгружает и дает скачать файл)
            if c1.button(f"✅ Завершить и отгрузить ({len(idx)})", key=f"ship_{key}"):
                with engine.connect() as conn:
                    for _, r in selected_rows.iterrows():
                        conn.execute(text("INSERT INTO archive SELECT *, :d FROM stock WHERE uuid=:u"), 
                                    {"d": datetime.now().strftime("%d.%m %H:%M"), "u": r['uuid']})
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": r['uuid']})
                    conn.commit()
                st.session_state[f"last_file_{key}"] = out.getvalue()
                reset_selection()
                st.rerun()

            if f"last_file_{key}" in st.session_state:
                st.download_button("📥 СКАЧАТЬ ЛИСТ ОТГРУЗКИ (EXCEL)", st.session_state[f"last_file_{key}"], 
                                   f"delivery_{storage_type}.xlsx", type="primary")

            if c2.button(f"🗑️ Удалить ({len(idx)})", key=f"del_{key}"):
                with engine.connect() as conn:
                    for i in idx: conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": df.iloc[i]['uuid']})
                    conn.commit()
                reset_selection()
                st.rerun()
    else: st.info(f"Склад {storage_type} пуст")

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    arch_type = st.radio("Архив:", ["ИП", "ООО"], horizontal=True, key="arch_sel")
    df_arch = pd.read_sql(text(f"SELECT * FROM archive WHERE type='{arch_type}'"), engine)
    if not df_arch.empty:
        st.dataframe(df_arch, use_container_width=True, hide_index=True)
        # Возможность скачать весь архив (дублирование функции)
        out_a = io.BytesIO()
        df_arch.to_excel(out_a, index=False)
        st.download_button(f"📥 Скачать весь архив {arch_type}", out_a.getvalue(), f"archive_{arch_type}.xlsx")
    else: st.info("Архив пуст")

with t4:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    boxes = len(df_all)
    pallets = math.ceil(boxes / 16) if boxes > 0 else 0
    st.metric("Коробов", boxes), st.metric("Паллет", pallets)
    st.write(f"Стоимость: {pallets * 50} ₽/сут")

with t5:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    if not df_all.empty:
        res = df_all.groupby(["type", "barcode"])["quantity"].sum().reset_index()
        res.columns = ["Тип", "Баркод", "Общее количество"]
        st.dataframe(res, use_container_width=True, hide_index=True)
