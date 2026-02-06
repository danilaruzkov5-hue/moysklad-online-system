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

st.set_page_config(layout="wide", page_title="Склад")

# --- API ---
def load_api_data():
    url = f"https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000&filter=store=https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}"
    try:
        res = requests.get(url, headers=HEADERS)
        return res.json().get('rows', []) if res.status_code == 200 else []
    except: return []

st.title("📦 Единая база склада")

# --- ПРИЕМКА ---
with st.sidebar:
    st.header("📥 Приемка")
    uploaded_file = st.file_uploader("Загрузи Excel", type=["xlsx"])
    target_type = st.radio("Тип поставки:", ["ИП", "ООО"])

    if uploaded_file and st.button("➕ Добавить"):
        try:
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"]
            ms_rows = load_api_data()
            mapping = {str(r.get('code')): (r.get('article', '-'), r.get('name', 'Неизвестно')) for r in ms_rows}
            
            with engine.connect() as conn:
                for _, row in new_data.iterrows():
                    art, name = mapping.get(str(row["Баркод"]), ("-", "Новый товар"))
                    uid = f"ID_{datetime.now().timestamp()}_{row['Баркод']}_{_}"
                    conn.execute(text("INSERT INTO stock VALUES (:u, :n, :a, :b, :q, :bn, :t)"),
                                {"u":str(uid), "n":str(name), "a":str(art), "b":str(row["Баркод"]), 
                                 "q":float(row["Кол-во"]), "bn":str(row["Номер короба"]), "t":str(target_type)})
                conn.commit()
            st.success("Готово!")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка: {e}")

search = st.text_input("🔍 Поиск")
t1, t2, t3, t4, t5 = st.tabs(["ИП", "ООО", "Архив", "Хранение", "Итого"])

def render_simple_table(storage_type, key):
    df = pd.read_sql(text(f"SELECT * FROM stock WHERE type='{storage_type}'"), engine)
    if search:
        df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
    
    if not df.empty:
        # Используем простую таблицу с выбором через Checkbox для стабильности
        selected_indices = []
        for i, row in df.iterrows():
            if st.checkbox(f"{row['name']} | Короб: {row['box_num']}", key=f"check_{key}_{i}"):
                selected_indices.append(i)
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        if selected_indices:
            c1, c2 = st.columns(2)
            if c1.button("✅ Отгрузить выбранное", key=f"btn_ship_{key}"):
                with engine.connect() as conn:
                    for idx in selected_indices:
                        r = df.iloc[idx]
                        conn.execute(text("INSERT INTO archive SELECT *, :d FROM stock WHERE uuid=:u"), {"d": datetime.now().strftime("%d.%m %H:%M"), "u": r['uuid']})
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": r['uuid']})
                    conn.commit()
                st.rerun()
    else: st.info("Пусто")
         with t1: render_simple_table("ИП", "ip")
with t2: render_simple_table("ООО", "ooo")

with t3:
    arch_df = pd.read_sql(text("SELECT * FROM archive"), engine)
    if not arch_df.empty:
        st.dataframe(arch_df, use_container_width=True, hide_index=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            arch_df.to_excel(writer, index=False)
        st.download_button("📥 Скачать Excel", output.getvalue(), "archive.xlsx")
        if st.button("🗑️ Очистить весь архив"):
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM archive"))
                conn.commit()
            st.rerun()
    else: st.info("Архив пуст")

with t4:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    boxes = len(df_all)
    pallets = math.ceil(boxes / 16) if boxes > 0 else 0
    st.metric("Паллет", pallets)
    st.write(f"Хранение: {pallets * 50} ₽/сут")

with t5:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    if not df_all.empty:
        res = df_all.groupby("barcode")["quantity"].sum().reset_index()
        st.dataframe(res, use_container_width=True, hide_index=True)



