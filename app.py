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

# 2. Функция списания
def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/entity/loss" # Проверь URL, иногда нужен /remap/1.2/
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{"quantity": float(quantity), "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}}]
    }
    res = requests.post(url, headers=HEADERS, json=data)
    return res.status_code == 201

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'df' not in st.session_state:
    df, status = load_initial_data()
    st.session_state.df = df
    st.session_state.api_connected = status
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

st.title("📦 Система управления складом (ОНЛАЙН)")

# МЕТРИКИ
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов на складе", total_boxes)
    c2.metric("Расчетное кол-во паллетов", pallets)
    c3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

# ПОИСК
search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Наименованию")

# ВКЛАДКИ
tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type, key_suffix):
    df = st.session_state.df
    # Фильтруем данные для текущей вкладки
    filtered_df = df[df["Направление(склад)"].str.contains(storage_type, na=False)].reset_index(drop=True)

    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) |
            filtered_df['Артикул'].astype(str).str.contains(sq) |
            filtered_df['Наименование'].str.lower().str.contains(sq)
        ]

    st.subheader(f"Остатки {key_suffix}")
    
    # Используем новый метод обработки выбора строк через st.column_config
    # Добавляем колонку с чекбоксами вручную через st.data_editor для надежности
    if not filtered_df.empty:
        filtered_df.insert(0, "Выбрать", False)
        
        edited_df = st.data_editor(
            filtered_df,
            column_config={"Выбрать": st.column_config.CheckboxColumn(required=True), "uuid": None}, # Скрываем uuid
            disabled=["Наименование", "Артикул", "Баркод товара(штрихкод)", "Кол-во", "Направление(склад)"],
            hide_index=True,
            use_container_width=True,
            key=f"editor_{key_suffix}"
        )
        qty = st.number_input("Сколько штук отгружаем?", min_value=1, value=1, key=f"q_{key_suffix}")

        if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ", key=f"btn_{key_suffix}"):
            # Находим строки, где стоит галочка
            selected_items = edited_df[edited_df["Выбрать"] == True]
            
            if not selected_items.empty:
                success_count = 0
                for index, item in selected_items.iterrows():
                    # 1. Списание в МойСклад
                    if create_ms_loss(item['uuid'], qty):
                        # 2. Подготовка для архива
                        item_to_archive = item.copy()
                        item_to_archive['Кол-во'] = qty
                        # Убираем колонку выбора для архива
                        item_to_archive = item_to_archive.drop("Выбрать")
                        
                        st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item_to_archive])], ignore_index=True)
                        
                        # 3. Удаляем из основной таблицы сессии
                        st.session_state.df = st.session_state.df[st.session_state.df['uuid'] != item['uuid']].reset_index(drop=True)
                        success_count += 1
                
                if success_count > 0:
                    st.success(f"Успешно отгружено позиций: {success_count}. Данные в МойСклад обновлены!")
                    st.rerun()
                else:
                    st.error("Ошибка при списании в МойСклад. Проверьте настройки API.")
            else:
                st.error("Сначала поставьте галочки в колонке 'Выбрать'!")
    else:
        st.info("Товары не найдены")

with tab1: render_tab("ИП", "ИП")
with tab2: render_tab("ООО", "ООО")
with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
        if st.button("🗑 Очистить архив"):
            st.session_state.archive = pd.DataFrame()
            st.rerun()
    else:
        st.info("Архив пока пуст")




