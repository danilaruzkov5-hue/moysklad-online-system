import streamlit as st
import pandas as pd
import requests
import sqlite3
import math
from datetime import datetime
import io

# --- НАСТРОЙКИ (ТВОИ ДАННЫЕ) ---

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace
# --- БАЗА ДАННЫХ (Для работы 10+ человек) ---
def get_db_connection():
    return sqlite3.connect("warehouse.db", check_same_thread=False)

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS stock 
        (uuid TEXT PRIMARY KEY, name TEXT, article TEXT, barcode TEXT, quantity REAL, box_num TEXT, type TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
        (uuid TEXT PRIMARY KEY, name TEXT, article TEXT, barcode TEXT, quantity REAL, box_num TEXT, type TEXT, ship_date TEXT)''')
    conn.commit()

init_db()

st.set_page_config(layout="wide", page_title="Складской Терминал")

# --- API МОЙСКЛАД ---
def load_api_data():
    # Фильтруем остатки именно по твоему складу
    url = f"https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000&filter=store=https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return res.json().get('rows', [])
    except:
        return []
    return []

def get_df_from_db(table="stock"):
    return pd.read_sql(f"SELECT * FROM {table}", get_db_connection())

# --- ИНТЕРФЕЙС ---
st.title("📦 Единая база склада (ИП / ООО)")

with st.sidebar:
    st.header("📥 Приемка товара")
    uploaded_file = st.file_uploader("Загрузи Excel (Баркод, Кол-во, Номер короба)", type=["xlsx"])
    target_type = st.radio("Тип поставки:", ["ИП", "ООО"])

    if uploaded_file and st.button("➕ Добавить на баланс"):
        try:
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"]
            
            # Поиск Артикула в МойСклад
            ms_rows = load_api_data()
            mapping = {str(r.get('code')): (r.get('article', '-'), r.get('name', 'Неизвестно')) for r in ms_rows}
            
            conn = get_db_connection()
            for _, row in new_data.iterrows():
                art, name = mapping.get(str(row["Баркод"]), ("-", "Новый товар"))
                uid = f"ID_{datetime.now().timestamp()}_{row['Баркод']}_{_}"
                conn.execute("INSERT INTO stock VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (uid, name, art, str(row["Баркод"]), row["Кол-во"], str(row["Номер короба"]), target_type))
            conn.commit()
            st.success("Данные добавлены в общую базу!")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка файла: {e}")

search = st.text_input("🔍 Быстрый поиск (Баркод / Артикул)")
t1, t2, t3, t4, t5 = st.tabs(["🏠 ИП", "🏢 ООО", "📜 Архив", "💰 Хранение", "📊 Итого"])

def render_table(storage_type, key):
    df = get_df_from_db("stock")
    filt = df[df["type"] == storage_type]
    
    if search:
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
    
    if not filt.empty:
        sel = st.dataframe(filt, use_container_width=True, hide_index=True, 
                           selection_mode="multi-row", on_select="rerun", key=f"t_{key}")
        idx = sel.get("selection", {}).get("rows", [])
        
        c1, c2 = st.columns(2)
        with c1:
            if idx and st.button(f"✅ Отгрузить в архив", key=f"b_{key}"):
                conn = get_db_connection()
                for _, r in filt.iloc[idx].iterrows():
                    conn.execute("INSERT INTO archive SELECT *, ? FROM stock WHERE uuid=?", (datetime.now().strftime("%d.%m %H:%M"), r['uuid']))
                    conn.execute("DELETE FROM stock WHERE uuid=?", (r['uuid'],))
                conn.commit()
                st.rerun()
        with c2:
            if idx and st.button(f"🗑️ Удалить безвозвратно", key=f"del_{key}"):
                conn = get_db_connection()
                uids = filt.iloc[idx]['uuid'].tolist()
                conn.executemany("DELETE FROM stock WHERE uuid=?", [(u,) for u in uids])
                conn.commit()
                st.rerun()
    else: st.info(f"На складе {storage_type} пока ничего нет")

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    arch_df = get_df_from_db("archive")
    if not arch_df.empty:
        sel_a = st.dataframe(arch_df, use_container_width=True, hide_index=True, selection_mode="multi-row", key="arch_t")
        
        # Скачивание Excel (Шаблон по ТЗ)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            out = arch_df[["barcode", "quantity", "box_num"]].copy()
            out.columns = ["Баркод", "Кол-во", "Номер короба"]
            out["Дата приемки"], out["ФИО сотрудника"] = "", ""
            out.to_excel(writer, index=False, sheet_name='Отгрузка')
        st.download_button("📥 Скачать Excel отгрузки", output.getvalue(), "otgruzka.xlsx")

        idx_a = sel_a.get("selection", {}).get("rows", [])
        if idx_a and st.button("🔙 Вернуть на баланс"):
            conn = get_db_connection()
            for _, r in arch_df.iloc[idx_a].iterrows():
                conn.execute("INSERT INTO stock SELECT uuid, name, article, barcode, quantity, box_num, type FROM archive WHERE uuid=?", (r['uuid'],))
                conn.execute("DELETE FROM archive WHERE uuid=?", (r['uuid'],))
            conn.commit()
            st.rerun()
    else: st.info("Архив пуст")

with t4:
    df_all = get_df_from_db("stock")
    boxes = len(df_all)
    pallets = math.ceil(boxes / 16) if boxes > 0 else 0
    st.metric("Всего коробов", boxes)
    st.metric("Паллет к оплате", pallets)
    st.metric("Стоимость/сутки", f"{pallets * 50} ₽")

with t5:
    df_all = get_df_from_db("stock")
    if not df_all.empty:
        res = df_all.groupby("barcode")["quantity"].sum().reset_index()
        res.columns = ["Баркод", "Общее количество"]
        st.dataframe(res, use_container_width=True, hide_index=True)


