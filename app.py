import streamlit as st
import pandas as pd
import requests
import math
import uuid
from datetime import datetime
import io

# --- ТВОИ ДАННЫЕ (ИЗ СКРИНШОТА) ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал МС")

# --- ФУНКЦИИ ---
def load_api_data():
    url = f"https://api.moysklad.ru/api/remap/1.2/report/stock/all?filter=store=https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID};organization=https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}&limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            rows = []
            for i in res.json().get('rows', []):
                name = i.get('name', '')
                rows.append({
                    "uuid": str(uuid.uuid4()),
                    "Наименование": name,
                    "Артикул": i.get('article', '-'),
                    "Баркод": i.get('code', '-'),
                    "Кол-во": i.get('stock', 0),
                    "Номер короба": "МС",
                    "Тип": "ИП" if "ИП" in name.upper() else "ООО"
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

# Инициализация состояний
if 'df' not in st.session_state:
    st.session_state.df = load_api_data()
if 'arch' not in st.session_state:
    st.session_state.arch = pd.DataFrame(columns=["uuid", "Наименование", "Артикул", "Баркод", "Кол-во", "Номер короба", "Тип"])

st.title("📦 Система управления складом")

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("📥 Приемка товара")
    uploaded_file = st.file_uploader("Загрузи Excel (Баркод, Кол-во, Короб)", type=["xlsx"])
    target_type = st.radio("Тип поставки", ["ИП", "ООО"])

    if uploaded_file and st.button("➕ Добавить на баланс"):
        try:
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"]
            upload_df = pd.DataFrame({
                "uuid": [str(uuid.uuid4()) for _ in range(len(new_data))],
                "Наименование": "Загружено из файла",
                "Артикул": "-",
                "Баркод": new_data["Баркод"],
                "Кол-во": new_data["Кол-во"],
                "Номер короба": new_data["Номер короба"],
                "Тип": target_type
            })
            st.session_state.df = pd.concat([st.session_state.df, upload_df], ignore_index=True)
            st.success(f"Добавлено {len(upload_df)} позиций")
        except:
            st.error("Ошибка в формате Excel")

# --- КНОПКА ОБНОВЛЕНИЯ ---
if st.button("🔄 Обновить остатки из МойСклад", use_container_width=True):
    api_df = load_api_data()
    manual_df = st.session_state.df[st.session_state.df["Номер короба"] != "МС"]
    st.session_state.df = pd.concat([api_df, manual_df], ignore_index=True)
    st.rerun()

search = st.text_input("🔍 Поиск по Баркоду или Артикулу")
t1, t2, t3, t4, t5 = st.tabs(["🔹 ИП", "🔸 ООО", "📜 Архив отгрузки", "💰 Хранение", "📊 Итого по Баркодам"])

def render_table(storage_type, key_suffix):
    df = st.session_state.df
    filt = df[df["Тип"] == storage_type]
    if search:
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]

    if filt.empty:
        st.info(f"На складе {storage_type} пусто")
    else:
        sel = st.dataframe(filt, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"t_{key_suffix}")
        idx = sel.get("selection", {}).get("rows", [])
        
        if idx and st.button(f"🚀 Завершить и отгрузить выбранное", key=f"b_{key_suffix}"):
            shipped = filt.iloc[idx].copy()
            st.session_state.arch = pd.concat([st.session_state.arch, shipped], ignore_index=True)
            st.session_state.df = st.session_state.df[~st.session_state.df["uuid"].isin(shipped["uuid"])]
            st.rerun()

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    if not st.session_state.arch.empty:
        sel_arch = st.dataframe(st.session_state.arch, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key="arch_t")
        
        # Генерация Excel (используем openpyxl вместо xlsxwriter)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            out_df = st.session_state.arch[["Баркод", "Кол-во", "Номер короба"]].copy()
            out_df["Дата отгрузки"] = datetime.now().strftime("%d.%m.%Y")
            out_df["Склад"] = st.session_state.arch["Тип"]
            out_df.to_excel(writer, index=False, sheet_name='Отгрузка')
        
        st.download_button("📥 Скачать Excel поставки", output.getvalue(), "postavka.xlsx", use_container_width=True)

        # ВОЗВРАТ ИЗ АРХИВА (Кнопка по ТЗ)
        arch_idx = sel_arch.get("selection", {}).get("rows", [])
        if arch_idx and st.button("⬅️ Вернуть выбранные короба в остатки"):
            to_return = st.session_state.arch.iloc[arch_idx].copy()
            # Добавляем обратно в основной список
            st.session_state.df = pd.concat([st.session_state.df, to_return], ignore_index=True)
            # Удаляем из архива по uuid
            st.session_state.arch = st.session_state.arch[~st.session_state.arch["uuid"].isin(to_return["uuid"])]
            st.rerun()
    else:
        st.info("Архив пуст")

with t4:
    # Расчет хранения 16 коробов = 1 паллет = 50р
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16) if total_boxes > 0 else 0
    st.metric("Всего коробов на остатке", total_boxes)
    st.metric("Итого паллет", pallets)
    st.metric("Стоимость хранения (сутки)", f"{pallets * 50} руб")

with t5:
    if not st.session_state.df.empty:
        summary = st.session_state.df.groupby("Баркод")["Кол-во"].sum().reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)

