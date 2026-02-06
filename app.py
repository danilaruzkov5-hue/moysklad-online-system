import streamlit as st
import pandas as pd
import math
import requests

# --- НАСТРОЙКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Функция загрузки данных (Добавлена отладка)
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                name = item.get('name', '')
                # Упрощаем фильтр: если в имени есть ООО — в ООО, иначе всё в ИП
                direction = "ООО" if "ООО" in name.upper() else "ИП"
                rows.append({
                    "uuid": item.get('id'),
                    "Наименование": name,
                    "Артикул": item.get('article', ''),
                    "Баркод товара(штрихкод)": item.get('code', ''),
                    "Кол-во": item.get('stock', 0),
                    "Направление(склад)": direction
                })
            return pd.DataFrame(rows)
        else:
            st.error(f"Ошибка МойСклад: {response.status_code}. Проверь токен!")
    except Exception as e:
        st.error(f"Ошибка подключения: {e}")
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

# Если данных нет или нажата кнопка обновления — загружаем
if 'df' not in st.session_state or st.sidebar.button("🔄 ОБНОВИТЬ ОСТАТКИ"):
    with st.spinner('Загрузка данных из МойСклад...'):
        st.session_state.df = load_initial_data()

st.title("📦 Система управления складом")

# Проверка на наличие данных перед отрисовкой
if st.session_state.df is None or st.session_state.df.empty:
    st.warning("⚠️ Данные для отображения не найдены. Попробуйте нажать кнопку обновления слева.")
    if st.button("Загрузить данные сейчас"):
        st.session_state.df = load_initial_data()
        st.rerun()
else:
    # МЕТРИКИ
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов", total_boxes)
    c2.metric("Паллетов", pallets)
    c3.metric("Хранение / сутки", f"{pallets * 50} ₽")

    st.divider()

    search_query = st.text_input("🔍 Поиск по Артикулу или Наименованию")
    tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

    def render_tab(storage_type, key_suffix):
        # Работаем с копией данных из сессии
        df_all = st.session_state.df.copy()
        filtered_df = df_all[df_all["Направление(склад)"] == storage_type].reset_index(drop=True)
        
        if search_query:
            sq = search_query.lower()
            filtered_df = filtered_df[
                filtered_df['Наименование'].str.lower().str.contains(sq) | 
                filtered_df['Артикул'].astype(str).str.lower().str.contains(sq)
            ]
            if filtered_df.empty:
            st.info(f"На складе {storage_type} товаров не найдено.")
            return

        # Таблица с выбором
        event = st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True,
            selection_mode="multi-row",
            on_select="rerun",
            key=f"table_{key_suffix}"
        )

        qty_to_ship = st.number_input("Кол-во для отгрузки", min_value=1, value=1, key=f"qty_{key_suffix}")

        if st.button(f"🚀 ОТГРУЗИТЬ ВЫБРАННОЕ ({storage_type})", key=f"btn_{key_suffix}"):
            selected_indices = event.get("selection", {}).get("rows", [])
            
            if selected_indices:
                ids_to_remove = []
                for idx in selected_indices:
                    item = filtered_df.iloc[idx].copy()
                    
                    # 1. Списание в МойСклад
                    create_ms_loss(item['uuid'], qty_to_ship)
                    
                    # 2. В архив
                    item['Отгружено'] = qty_to_ship
                    st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item])], ignore_index=True)
                    
                    # Запоминаем ID
                    ids_to_remove.append(item['uuid'])
                
                # 3. Удаляем из памяти сессии
                st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(ids_to_remove)].reset_index(drop=True)
                
                st.success("Товары отгружены!")
                st.rerun()
            else:
                st.error("Ничего не выбрано!")

    with tab1: render_tab("ИП", "ip")
    with tab2: render_tab("ООО", "ooo")
    with tab3:
        st.subheader("📜 Архив отгрузок")
        if not st.session_state.archive.empty:
            st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True)
        else:
            st.info("Архив пуст")


