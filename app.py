import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime
import io

# --- ТВОИ ДАННЫЕ (ОБЯЗАТЕЛЬНО ЗАПОЛНИ) ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал МС")

# --- ФУНКЦИИ ---
def load_api_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            rows = []
            for i in res.json().get('rows', []):
                name = i.get('name', '')
                rows.append({
                    "uuid": i.get('id'),
                    "Наименование": name,
                    "Артикул": i.get('article', '—'),
                    "Баркод": i.get('code', '—'),
                    "Кол-во": i.get('stock', 0),
                    "Номер короба": "МС", # Метка, что данные из МойСклад
                    "Тип": "ИП" if "ИП" in name.upper() else "ООО"
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

# Инициализация состояний
if 'df' not in st.session_state: st.session_state.df = load_api_data()
if 'arch' not in st.session_state: 
    st.session_state.arch = pd.DataFrame(columns=["uuid", "Наименование", "Артикул", "Баркод", "Кол-во", "Номер короба", "Тип"])

# --- ИНТЕРФЕЙС ---
st.title("📦 Система управления складом")

# Боковая панель: Приемка (Excel по ТЗ)
with st.sidebar:
    st.header("📥 Приемка товара")
    uploaded_file = st.file_uploader("Загрузи Excel (Баркод, Кол-во, Короб)", type=["xlsx"])
    target_type = st.radio("Тип поставки:", ["ИП", "ООО"])
    
    if uploaded_file and st.button("➕ Добавить на баланс"):
        try:
            # Читаем Excel. Предполагаем колонки: Баркод, Кол-во, Номер короба
            new_data = pd.read_excel(uploaded_file)
            new_data.columns = ["Баркод", "Кол-во", "Номер короба"] # Принудительно именуем
            new_data["Тип"] = target_type
            new_data["Наименование"] = "Загружено из файла"
            new_data["Артикул"] = "—"
            new_data["uuid"] = [f"file_{i}_{datetime.now().timestamp()}" for i in range(len(new_data))]
            
            st.session_state.df = pd.concat([st.session_state.df, new_data], ignore_index=True)
            st.success(f"Добавлено {len(new_data)} позиций!")
        except Exception as e:
            st.error(f"Ошибка в файле: {e}")

# Основная рабочая область
if st.button("🔄 Обновить остатки из МойСклад", use_container_width=True):
    fresh_df = load_api_data()
    if not st.session_state.arch.empty:
        arch_ids = st.session_state.arch['uuid'].tolist()
        st.session_state.df = fresh_df[~fresh_df['uuid'].isin(arch_ids)].reset_index(drop=True)
    else:
        st.session_state.df = fresh_df
    st.rerun()

search = st.text_input("🔍 Поиск по Баркоду или Артикулу")

t1, t2, t3, t4, t5 = st.tabs(["📦 ИП", "🏢 ООО", "📜 Архив отгрузки", "💰 Хранение", "📊 Итого по Баркодам"])

def render_table(storage_type, key):
    df = st.session_state.df
    filt = df[df["Тип"] == storage_type]
    if search:
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]

    if filt.empty:
        st.info(f"На складе {storage_type} пусто")
    else:
        sel = st.dataframe(filt, use_container_width=True, hide_index=True, 
                           selection_mode="multi-row", on_select="rerun", key=f"t_{key}")
        
        idx = sel.get("selection", {}).get("rows", [])
        if idx and st.button(f"🚀 Завершить и отгрузить ({storage_type})", key=f"b_{key}"):
            shipped = filt.iloc[idx].copy()
            st.session_state.arch = pd.concat([st.session_state.arch, shipped], ignore_index=True)
            st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(shipped['uuid'])]
            st.rerun()

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    if not st.session_state.arch.empty:
        st.dataframe(st.session_state.arch, use_container_width=True, hide_index=True)
        
        # Генерация Excel для склада по шаблону заказчика
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            out_df = st.session_state.arch[["Баркод", "Кол-во", "Номер короба"]].copy()
            # Добавляем пустые колонки для ручного заполнения на складе (как в ТЗ)
            out_df["Дата приемки"] = ""
            out_df["ФИО сотрудника"] = ""
            out_df.to_excel(writer, index=False, sheet_name='Отгрузка')
        
        st.download_button("📥 Завершить и скачать Excel поставки", output.getvalue(), "postavka.xlsx", use_container_width=True)
        
        if st.button("⏪ Вернуть короба на склад"):
            st.session_state.df = pd.concat([st.session_state.df, st.session_state.arch], ignore_index=True)
            st.session_state.arch = st.session_state.arch.iloc[0:0]
            st.rerun()
    else: st.info("Архив пуст")

with t4:
    # 16 коробов = 1 паллет = 50 руб
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16) if total_boxes > 0 else 0
    st.metric("Всего коробов на остатке", total_boxes)
    st.metric("Итого паллет", pallets)
    st.metric("Стоимость хранения (сутки)", f"{pallets * 50} руб")
    st.caption("Расчет фиксируется ежедневно.")

with t5:
    if not st.session_state.df.empty:
        st.subheader("Сводка общего количества по баркодам")
        summary = st.session_state.df.groupby("Баркод")["Кол-во"].sum().reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)




