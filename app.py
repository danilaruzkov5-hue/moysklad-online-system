import streamlit as st
import pandas as pd
import math
import requests
import os

# Константы
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
STOCK_FILE = 'current_stock.csv'
ARCHIVE_FILE = 'archive_stock.csv'

st.set_page_config(layout="wide", page_title="Складской Терминал")
st.title("📦 Система управления складом")

# --- ФУНКЦИИ СОХРАНЕНИЯ ---
def save_data():
    st.session_state.df.to_csv(STOCK_FILE, index=False)
    st.session_state.archive.to_csv(ARCHIVE_FILE, index=False)

@st.cache_data
def load_initial_data():
    try:
        url = "https://api.moysklad.ru/api/remap/1.2/entity/product"
        headers = {"Authorization": f"Bearer {TOKEN}"}
        response = requests.get(url, headers=headers, params={"limit": 1})
        api_status = response.status_code == 200
    except:
        api_status = False

    if os.path.exists(STOCK_FILE):
        df = pd.read_csv(STOCK_FILE)
    else:
        try:
            df = pd.read_excel('Выгрузка.xlsx')
        except:
            df = pd.DataFrame()

    if os.path.exists(ARCHIVE_FILE):
        archive = pd.read_csv(ARCHIVE_FILE)
    else:
        archive = pd.DataFrame()

    if not df.empty:
        df['Направление(склад)'] = df['Направление(склад)'].fillna('ИП')
        if 'Артикул' not in df.columns:
            df['Артикул'] = "Арт-" + df['Баркод товара(штрихкод)'].astype(str).str[-4:]
            
    return df, archive, api_status

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'df' not in st.session_state:
    df, archive, status = load_initial_data()
    st.session_state.df = df
    st.session_state.archive = archive
    st.session_state.api_connected = status

# Индикатор связи
if st.session_state.api_connected:
    st.success("🟢 Связь с МойСклад установлена")
else:
    st.warning("🟡 Работа в автономном режиме")

# --- МЕТРИКИ ---
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16) if total_boxes > 0 else 0
    daily_cost = pallets * 50
    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.metric("Всего коробов на складе", total_boxes)
    col_info2.metric("Расчетное кол-во паллетов", pallets)
    col_info3.metric("Стоимость хранения / сутки", f"{daily_cost} ₽")

st.divider()

# --- ПОИСК ---
search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Номеру короба")

# --- ВКЛАДКИ ---
tab1, tab2, tab3 = st.tabs(["📊 Остатки ИП", "🏢 Остатки ООО", "📦 Архив отгрузок"])

def render_tab(storage_type_filter, key_suffix):
    # Фильтруем данные для отображения
    mask = st.session_state.df['Направление(склад)'].str.contains(storage_type_filter, na=False)
    filtered_df = st.session_state.df[mask]
    
    if search_query:
        sq = str(search_query).lower()
        filtered_df = filtered_df[
            filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) | 
            filtered_df['Порядковый номер короба склада'].astype(str).str.contains(sq) |
            filtered_df['Артикул'].astype(str).lower().str.contains(sq)
        ]

    st.subheader(f"Остатки {key_suffix}")
    if filtered_df.empty:
        st.info("В этой категории товаров нет")
        return

    # Отображаем таблицу
    event = st.dataframe(filtered_df, use_container_width=True, on_select="rerun", selection_mode="multi-row", key=f"table_{key_suffix}")
    
    # Логика отгрузки
    if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННЫЕ", key=f"btn_{key_suffix}"):
        if event.selection.rows:
            # Получаем реальные индексы из отфильтрованного DF
            selected_indices = filtered_df.index[event.selection.rows]
            
            # Копируем в архив
            shipped_items = st.session_state.df.loc[selected_indices]
            st.session_state.archive = pd.concat([st.session_state.archive, shipped_items], ignore_index=True)
            # Удаляем из основного состава
            st.session_state.df = st.session_state.df.drop(selected_indices).reset_index(drop=True)
            
            save_data()
            st.rerun()
        else:
            st.error("Сначала выделите строки галочками!")

with tab1:
    render_tab('ИП|Не указано', "ИП")

with tab2:
    render_tab('ООО|Юр лицо', "ООО")

with tab3:
    st.subheader("📦 Архив отгрузок")
    if st.session_state.archive.empty:
        st.info("Архив пока пуст")
    else:
        arc_event = st.dataframe(st.session_state.archive, use_container_width=True, on_select="rerun", selection_mode="multi-row", key="arc_table")
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📥 Скачать отчет", st.session_state.archive.to_csv(index=False).encode('utf-8-sig'), "otgruzka.csv")
        with c2:
            if st.button("🔄 ВЕРНУТЬ НА СКЛАД"):
                if arc_event.selection.rows:
                    idx = arc_event.selection.rows
                    to_return = st.session_state.archive.iloc[idx]
                    st.session_state.df = pd.concat([st.session_state.df, to_return], ignore_index=True)
                    st.session_state.archive = st.session_state.archive.drop(st.session_state.archive.index[idx]).reset_index(drop=True)
                    save_data()
                    st.rerun()