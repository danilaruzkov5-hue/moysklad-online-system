import streamlit as st
import pandas as pd
import math
import requests
import io

# --- 1. НАСТРОЙКИ (ОБЯЗАТЕЛЬНО ВСТАВЬ СВОИ ID) ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# --- 2. ФУНКЦИИ API ---
def load_initial_data():
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            rows = []
            for item in data.get('rows', []):
                name = item.get('name', '')
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
    except:
        pass
    return pd.DataFrame()

def create_ms_loss(product_id, quantity):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/loss"
    data = {
        "organization": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/organization/{ORG_ID}", "type": "organization", "mediaType": "application/json"}},
        "store": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/store/{STORE_ID}", "type": "store", "mediaType": "application/json"}},
        "positions": [{"quantity": float(quantity), "assortment": {"meta": {"href": f"https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}", "type": "product", "mediaType": "application/json"}}}]
    }
    requests.post(url, headers=HEADERS, json=data)

# --- 3. СОСТОЯНИЕ (SESSION STATE) ---
if 'archive' not in st.session_state:
    st.session_state.archive = pd.DataFrame()

if 'df' not in st.session_state:
    st.session_state.df = load_initial_data()

# --- 4. ИНТЕРФЕЙС ---
st.title("📦 Система управления складом")

if st.sidebar.button("🔄 ОБНОВИТЬ ОСТАТКИ"):
    st.session_state.df = load_initial_data()
    st.rerun()

# Метрики
if not st.session_state.df.empty:
    total_boxes = len(st.session_state.df)
    pallets = math.ceil(total_boxes / 16)
    c1, c2, c3 = st.columns(3)
    c1.metric("Всего коробов", total_boxes)
    c2.metric("Расчетное кол-во паллетов", pallets)
    c3.metric("Стоимость хранения / сутки", f"{pallets * 50} ₽")

st.divider()

search_query = st.text_input("🔍 Поиск по Артикулу или Наименованию")
tab1, tab2, tab3 = st.tabs(["📦 Остатки ИП", "🏢 Остатки ООО", "📜 Архив отгрузок"])

def render_tab(storage_type, key_suffix):
    df_all = st.session_state.df
    if df_all.empty:
        st.warning("Нет данных.")
        return

    filtered_df = df_all[df_all["Направление(склад)"] == storage_type].reset_index(drop=True)
    
    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[filtered_df['Наименование'].str.lower().str.contains(sq) | filtered_df['Артикул'].astype(str).str.lower().str.contains(sq)]

    if filtered_df.empty:
        st.info(f"На складе {storage_type} пусто.")
        return

    event = st.dataframe(filtered_df, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun", key=f"t_{key_suffix}")
    qty = st.number_input("Кол-во", min_value=1, value=1, key=f"q_{key_suffix}")

    if st.button(f"🚀 ОТГРУЗИТЬ ({storage_type})", key=f"b_{key_suffix}"):
        selected = event.get("selection", {}).get("rows", [])
        if selected:
            ids_to_remove = []
            for idx in selected:
                item = filtered_df.iloc[idx].copy()
                create_ms_loss(item['uuid'], qty)
                item['Отгружено'] = qty
                st.session_state.archive = pd.concat([st.session_state.archive, pd.DataFrame([item])], ignore_index=True)
                ids_to_remove.append(item['uuid'])
            st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(ids_to_remove)].reset_index(drop=True)
            st.rerun()
        else:
            st.error("Выдели товары!")

with tab1: render_tab("ИП", "ip")
with tab2: render_tab("ООО", "ooo")

with tab3:
    st.subheader("📜 Архив отгрузок")
    if not st.session_state.archive.empty:
        arch_event = st.dataframe(st.session_state.archive, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun", key="arch_t")
        
        ca1, ca2 = st.columns(2)
        with ca1:
            if st.button("⬅️ ВЕРНУТЬ В ОСТАТКИ", use_container_width=True):
                sel_arch = arch_event.get("selection", {}).get("rows", [])
                if sel_arch:
                    items_ret = st.session_state.archive.iloc[sel_arch]
                    st.session_state.df = pd.concat([st.session_state.df, items_ret], ignore_index=True)
                    st.session_state.archive = st.session_state.archive[~st.session_state.archive['uuid'].isin(items_ret['uuid'])].reset_index(drop=True)
                    st.rerun()
        with ca2:
            df_exp = st.session_state.archive.drop(columns=['uuid']) if 'uuid' in st.session_state.archive.columns else st.session_state.archive
            csv = df_exp.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 СКАЧАТЬ АРХИВ (CSV)", data=csv, file_name="otgruzka.csv", mime="text/csv", use_container_width=True)
    else:
        st.info("Архив пуст.")

