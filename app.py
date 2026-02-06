import streamlit as st
import pandas as pd
import math
import requests

# --- КОНСТАНТЫ ---
TOKEN = "4cbd6f585d0c15ea2506a6f82fbdb8a69a49c422"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc"
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал Онлайн")

# 1. Загрузка данных из МойСклад
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                rows.append({
                    "uuid": item.get('id'),
                    "Наименование": item.get('name'),
                    "Артикул": item.get('article', ''),
                    "Баркод товара(штрихкод)": item.get('code', ''),
                    "Кол-во": item.get('stock', 0),
                    "Направление(склад)": "ИП" if "ИП" in item.get('name', '') else "ООО"
                })
            return pd.DataFrame(rows), True
    except:
        pass
    return pd.DataFrame(), False

# 2. Функция списания (Исправлен URL и структура)
def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/loss"
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{
            "quantity": float(quantity),
            "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}
        }]
    }
    try:
        res = requests.post(url, headers=HEADERS, json=data)
        return res.status_code == 201
    except:
        return False

# --- ИНИЦИАЛИЗАЦИЯ ---
# Инициализируем архив, если его нет
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

# Загружаем данные из МС только если их еще нет в памяти
if 'df' not in st.session_state:
    df, status = load_initial_data()
    st.session_state.df = df
    st.session_state.api_connected = status

# Кнопка для ручного обновления остатков (в сайдбаре или сверху)
if st.sidebar.button("🔄 Обновить данные из МойСклад"):
    df, status = load_initial_data()
    st.session_state.df = df
    st.session_state.api_connected = status
    st.rerun()

st.title("📦 Система управления складом (ОНЛАЙН)")

# МЕТРИКИ (Как на скриншоте 1000011681)
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов на складе", total_boxes)
    c2.metric("Расчетное кол-во паллетов", pallets)
    c3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Наименованию")

tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type, key_suffix):
    df = st.session_state.df
    filtered_df = df[df["Направление(склад)"].str.contains(storage_type, na=False)].reset_index(drop=True)

    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) |
            filtered_df['Артикул'].astype(str).str.contains(sq) |
            filtered_df['Наименование'].str.lower().str.contains(sq)
        ]

    st.subheader(f"Остатки {key_suffix}")
    
    if not filtered_df.empty:
        # Добавляем колонку выбора
        display_df = filtered_df.copy()
        display_df.insert(0, "Выбрать", False)
        
        edited_df = st.data_editor(
            display_df,
            column_config={"Выбрать": st.column_config.CheckboxColumn(), "uuid": None},
            disabled=["Наименование", "Артикул", "Баркод товара(штрихкод)", "Кол-во", "Направление(склад)"],
            hide_index=True,
            use_container_width=True,
            key=f"ed_{key_suffix}"
        )

        qty = st.number_input("Сколько штук отгружаем?", min_value=1, value=1, key=f"q_{key_suffix}")
        if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ", key=f"btn_{key_suffix}"):
            selected_items = edited_df[edited_df["Выбрать"] == True]
            
            if not selected_items.empty:
            for _, item in selected_items.iterrows():
                create_ms_loss(item['uuid'], qty) # Списываем в облаке
                
                # Добавляем в архив
                arch_item = item.copy()
                arch_item['Кол-во'] = qty
                st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([arch_item.drop("Выбрать")])], ignore_index=True)
                
                # УДАЛЯЕМ из текущей таблицы в памяти (чтобы он исчез с экрана)
                st.session_state.df = st.session_state.df[st.session_state.df['uuid'] != item['uuid']].reset_index(drop=True)
            
            st.success("Отгрузка зафиксирована и убрана из текущих остатков!")
            st.rerun() # Перезапускаем интерфейс, чтобы увидеть изменения
            else:
                st.error("Ничего не выбрано!")

with tab1: render_tab("ИП", "ИП")
with tab2: render_tab("ООО", "ООО")
with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
        if st.button("🗑 Очистить архив"):
            st.session_state.archive = pd.DataFrame()
            st.rerun()






