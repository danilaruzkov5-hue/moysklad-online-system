import streamlit as st
import pandas as pd
import requests
import math

# --- НАСТРОЙКИ (Вставь свои ID) ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал")

# 1. Функция загрузки товаров (видит всё, что на твоем фото)
def load_data():
    # Запрашиваем остатки, чтобы видеть только то, что реально есть на складе
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            rows = []
            for i in res.json().get('rows', []):
                name = i.get('name', '')
                # Определяем ИП или ООО по названию (как в ТЗ)
                stype = "ИП" if "ИП" in name.upper() else "ООО"
                rows.append({
                    "uuid": i.get('id'),
                    "Наименование": name,
                    "Артикул": i.get('article', '—'),
                    "Баркод": i.get('code', '—'), # Поле 'Код' с твоего фото
                    "Кол-во": i.get('stock', 0),
                    "Тип": stype
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

# Инициализация данных
if 'df' not in st.session_state:
    st.session_state.df = load_data()
if 'arch' not in st.session_state:
    st.session_state.arch = pd.DataFrame()

st.title("📦 Управление складом")

# Кнопка обновления данных из МойСклад
if st.button("🔄 Обновить остатки из МойСклад"):
    st.session_state.df = load_data()
    st.rerun()

search = st.text_input("🔍 Поиск по названию, коду или артикулу")

t1, t2, t3, t4 = st.tabs(["📦 ИП", "🏢 ООО", "📜 Архив отгрузки", "💰 Хранение"])

def render_table(storage_type, key):
    df = st.session_state.df
    if df.empty:
        st.warning("Товары не найдены. Проверь TOKEN и ID склада.")
        return

    # Фильтр по ИП/ООО и поиску
    filt = df[df["Тип"] == storage_type]
    if search:
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]

    if filt.empty:
        st.info(f"Нет товаров для {storage_type}")
        return

    # Отображение таблицы
    sel = st.dataframe(filt, use_container_width=True, hide_index=True, 
                       selection_mode="multi-row", on_select="rerun", key=f"table_{key}")
    
    # Логика отгрузки
    selected_rows = sel.get("selection", {}).get("rows", [])
    if selected_rows:
        if st.button(f"🚀 Отгрузить выбранное ({storage_type})", key=f"btn_{key}"):
            items_to_ship = filt.iloc[selected_rows].copy()
            # Добавляем в архив
            st.session_state.arch = pd.concat([st.session_state.arch, items_to_ship], ignore_index=True)
            # Убираем из текущего списка (имитация отгрузки)
            st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(items_to_ship['uuid'])]
            st.success("Товары перенесены в архив!")
            st.rerun()

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    if not st.session_state.arch.empty:
        st.dataframe(st.session_state.arch, use_container_width=True, hide_index=True)
        csv = st.session_state.arch.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать файл отгрузки (Excel/CSV)", csv, "shipment.csv", "text/csv")
    else:
        st.info("Архив пуст")

with t4:
    total_items = int(st.session_state.df["Кол-во"].sum())
    # Твоя формула: 16 коробов = 1 паллет = 50 руб
    pallets = math.ceil(total_items / 16) if total_items > 0 else 0
    daily_cost = pallets * 50
    st.metric("Всего товаров на складе", total_items)
    st.metric("Расчетное кол-во паллет", pallets)
    st.metric("Стоимость хранения в сутки", f"{daily_cost} руб.")


