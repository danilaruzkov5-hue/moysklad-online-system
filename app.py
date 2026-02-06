import streamlit as st
import pandas as pd
import math
import requests

# --- КОНСТАНТЫ (ВСТАВЬ СВОИ ДАННЫЕ) ---
TOKEN = "bdcc5b722dd8bad73b205be6fff08267da7c121a"
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
            return pd.DataFrame(rows)
    except:
        pass
    return pd.DataFrame()

# 2. Функция списания
def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/loss"
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{"quantity": float(quantity), "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}}]
    }
    try:
        res = requests.post(url, headers=HEADERS, json=data)
        return res.status_code == 201
    except:
        return False

# --- ИНИЦИАЛИЗАЦИЯ ---
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()
if 'df' not in st.session_state:
    st.session_state.df = load_initial_data()

st.title("📦 Система управления складом (ОНЛАЙН)")

# МЕТРИКИ (Скриншот 1000011681)
if st.session_state.df is not None and not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов на складе", total_boxes)
    c2.metric("Расчетное кол-во паллетов", pallets)
    c3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

# ПОИСК И ВКЛАДКИ
search_query = st.text_input("🔍 Поиск по Баркоду, Артикулу или Наименованию")
tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type, key_suffix):
    df = st.session_state.df
    if df is None or df.empty:
        st.info("Нет данных")
        return

    # Фильтрация
    filtered_df = df[df["Направление(склад)"].str.contains(storage_type, na=False)].reset_index(drop=True)
    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['Баркод товара(штрихкод)'].astype(str).str.contains(sq) |
            filtered_df['Артикул'].astype(str).str.contains(sq) |
            filtered_df['Наименование'].str.lower().str.contains(sq)
        ]

    st.subheader(f"Остатки на складе {key_suffix}")
    
    # ТАБЛИЦА С ВЫБОРОМ (Как на видео 1000011581)
    event = st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=f"table_{key_suffix}"
    )

    st.write("") # Отступ
    qty = st.number_input("Сколько штук отгружаем?", min_value=1, value=1, key=f"qty_{key_suffix}")
    if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ ({key_suffix})", key=f"btn_{key_suffix}"):
        selected_rows = event.get("selection", {}).get("rows", [])
        if selected_rows:
            for row_idx in selected_rows:
                item = filtered_df.iloc[row_idx].copy()
                
                # 1. Списание в МС
                create_ms_loss(item['uuid'], qty)
                
                # 2. В архив
                item['Кол-во'] = qty
                st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item])], ignore_index=True)
                
                # 3. Удаляем из памяти
                st.session_state.df = st.session_state.df[st.session_state.df['uuid'] != item['uuid']].reset_index(drop=True)
            
            st.success("Готово! Товар списан и перемещен в архив.")
            st.rerun()
        else:
            st.error("Сначала выделите строки в таблице!")

with tab1:
    render_tab("ИП", "ИП")

with tab2:
    render_tab("ООО", "ООО")

with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
        if st.button("🗑 Очистить архив"):
            st.session_state.archive = pd.DataFrame()
            st.rerun()
    else:
        st.info("Архив пуст")



