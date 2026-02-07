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

st.set_page_config(layout="wide", page_title="Складской Терминал МС")

# --- API МОЙСКЛАД ---
def load_api_data():
    url = f"https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000&filter=store=https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}"
    try:
        res = requests.get(url, headers=HEADERS)
        return res.json().get('rows', []) if res.status_code == 200 else []
    except: return []

# Проверка связи для заказчика
ms_data = load_api_data()
connection_status = "🟢 Связь с МойСклад: Установлена" if ms_data else "🔴 Связь с МойСклад: Ошибка"

st.title("📦 Единая база склада (ИП / ООО)")
st.caption(connection_status)

# --- ПРИЕМКА ТОВАРА ---
with st.sidebar:
    st.header("📥 Приемка")
    uploaded_file = st.file_uploader("Загрузи Excel (Баркод, Кол-во, Короб)", type=["xlsx"])
    target_type = st.radio("Тип поставки:", ["ИП", "ООО"])

    if uploaded_file and st.button("➕ Добавить на баланс"):
        try:
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"]
            mapping = {str(r.get('code')): (r.get('article', '-'), r.get('name', 'Неизвестно')) for r in ms_data}
            
            with engine.connect() as conn:
                for _, row in new_data.iterrows():
                    art, name = mapping.get(str(row["Баркод"]), ("-", "Новый товар"))
                    uid = f"ID_{datetime.now().timestamp()}_{row['Баркод']}_{_}"
                    conn.execute(text("INSERT INTO stock VALUES (:u, :n, :a, :b, :q, :bn, :t)"),
                                {"u":str(uid), "n":str(name), "a":str(art), "b":str(row["Баркод"]), 
                                 "q":float(row["Кол-во"]), "bn":str(row["Номер короба"]), "t":str(target_type)})
                conn.commit()
            st.success("Данные успешно приняты!")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка файла: {e}")

search = st.text_input("🔍 Быстрый поиск по складу (Баркод / Артикул / Короб)")
t1, t2, t3, t4, t5 = st.tabs(["🏠 Склад ИП", "🏢 Склад ООО", "📜 Архив отгрузок", "💰 Хранение", "📊 Итого"])

def render_warehouse(storage_type, key):
    df = pd.read_sql(text(f"SELECT * FROM stock WHERE type='{storage_type}'"), engine)
    if search:
        df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
    
    if not df.empty:
        # Важно: используем UUID как индекс для точности выбора
        sel = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"main_{key}")
        selected_indices = sel.get("selection", {}).get("rows", [])
        
        if selected_indices:
            st.write(f"Выбрано для отгрузки: {len(selected_indices)} коробов")
            c1, c2 = st.columns(2)
            # КНОПКА ЗАВЕРШИТЬ (ОТГРУЗИТЬ) + СКАЧАТЬ
            if c1.button(f"🚀 Завершить и отгрузить ({storage_type})", key=f"btn_ship_{key}"):
                selected_rows = df.iloc[selected_indices]
                
                # Формируем Excel файл отгрузки по ТЗ
                export_df = selected_rows[['barcode', 'quantity', 'box_num']].copy()
                export_df.columns = ["Баркод", "Кол-во", "Номер короба"]
                export_df["Дата приемки"] = datetime.now().strftime("%d.%m.%Y")
                export_df["ФИО сотрудника"] = ""
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, index=False, sheet_name='Лист отгрузки')
                
                # Переносим в архив и удаляем со склада
                with engine.connect() as conn:
                    for _, r in selected_rows.iterrows():
                        conn.execute(text("INSERT INTO archive SELECT *, :d FROM stock WHERE uuid=:u"), {"d": datetime.now().strftime("%d.%m %H:%M"), "u": r['uuid']})
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": r['uuid']})
                    conn.commit()
                
                st.download_button("📥 Скачать лист отгрузки (Excel)", output.getvalue(), f"otgruzka_{storage_type}_{datetime.now().strftime('%d_%m')}.xlsx")
                st.info("Товары перенесены в архив. Скачайте файл выше.")
                # st.rerun() убираем здесь, чтобы кнопка скачивания не исчезла сразу

            if c2.button(f"🗑️ Удалить безвозвратно", key=f"btn_del_{key}"):
                with engine.connect() as conn:
                    for i in selected_indices:
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": df.iloc[i]['uuid']})
                    conn.commit()
                st.rerun()
    else: st.info(f"На складе {storage_type} пусто")

with t1: render_warehouse("ИП", "ip")
with t2: render_warehouse("ООО", "ooo")

with t3:
    st.subheader("Раздельный архив отгрузок")
    arch_type = st.radio("Показать архив:", ["ИП", "ООО"], horizontal=True)
    df_arch = pd.read_sql(text(f"SELECT * FROM archive WHERE type='{arch_type}'"), engine)
    
    if not df_arch.empty:
        sel_a = st.dataframe(df_arch, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"arch_tab_{arch_type}")
        idx_a = sel_a.get("selection", {}).get("rows", [])
        
        if idx_a:
            ca1, ca2 = st.columns(2)
            if ca1.button(f"🔙 Вернуть на баланс {arch_type}"):
                with engine.connect() as conn:
                    for i in idx_a:
                        r = df_arch.iloc[i]
                        conn.execute(text("INSERT INTO stock SELECT uuid, name, article, barcode, quantity, box_num, type FROM archive WHERE uuid=:u"), {"u": r['uuid']})
                        conn.execute(text("DELETE FROM archive WHERE uuid=:u"), {"u": r['uuid']})
                    conn.commit()
                st.rerun()
            if ca2.button(f"🔥 Очистить архив {arch_type}"):
                with engine.connect() as conn:
                    for i in idx_a:
                        conn.execute(text("DELETE FROM archive WHERE uuid=:u"), {"u": df_arch.iloc[i]['uuid']})
                    conn.commit()
                st.rerun()
    else: st.info(f"Архив {arch_type} пуст")

with t4:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    boxes = len(df_all)
    pallets = math.ceil(boxes / 16) if boxes > 0 else 0
    st.metric("Всего коробов на складе", boxes)
    st.metric("Паллет к оплате (1 паллет = 16 кор.)", pallets)
    st.subheader(f"Стоимость хранения: {pallets * 50} ₽ / сутки")
    with t5:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    if not df_all.empty:
        res = df_all.groupby(["type", "barcode"])["quantity"].sum().reset_index()
        res.columns = ["Юр. Лицо", "Баркод", "Общий остаток (шт)"]
        st.dataframe(res, use_container_width=True, hide_index=True)
