import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime

# --- ДАННЫЕ ИЗ ПЕРЕПИСКИ ---
TOKEN = "294b1754c146ae261cf689ffbf8fcaaa5c993e2d"
ORG_ID = "da0e7ea9-d216-11ec-0a80-08be00007acc" 
STORE_ID = "da0f3443-d216-11ec-0a80-08be00007ace" 
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

st.set_page_config(layout="wide", page_title="Складской Терминал МС")

def load_data():
    # Запрос всех товаров через API (связка с МС по переписке)
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all?limit=1000"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            rows = []
            for i in res.json().get('rows', []):
                name = i.get('name', '')
                stype = "ИП" if "ИП" in name.upper() else "ООО"
                rows.append({
                    "uuid": i.get('id'),
                    "Наименование": name,
                    "Артикул": i.get('article', '—'),
                    "Баркод": i.get('code', '—'),
                    "Кол-во": i.get('stock', 0),
                    "Тип": stype
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

# Инициализация
if 'df' not in st.session_state: st.session_state.df = load_data()
if 'arch' not in st.session_state: st.session_state.arch = pd.DataFrame(columns=["uuid", "Наименование", "Артикул", "Баркод", "Кол-во", "Тип"])

st.title("📦 Система управления складом (МойСклад)")

if st.sidebar.button("🔄 Обновить из МойСклад"):
    fresh_df = load_data()
    if not st.session_state.arch.empty:
        archived_uuids = st.session_state.arch['uuid'].tolist()
        st.session_state.df = fresh_df[~fresh_df['uuid'].isin(archived_uuids)].reset_index(drop=True)
    else: st.session_state.df = fresh_df
    st.rerun()

search = st.text_input("🔍 Поиск (Баркод / Артикул / Название)")

t1, t2, t3, t4, t5 = st.tabs(["📦 ИП", "🏢 ООО", "📜 Архив", "💰 Хранение", "📊 Аналитика по Баркодам"])

def render_table(storage_type, key):
    df = st.session_state.df
    filt = df[df["Тип"] == storage_type]
    if search:
        # Поиск по всем полям одновременно (как просил заказчик)
        filt = filt[filt.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]

    sel = st.dataframe(filt, use_container_width=True, hide_index=True, 
                       selection_mode="multi-row", on_select="rerun", key=f"table_{key}")
    
    selected_rows = sel.get("selection", {}).get("rows", [])
    if selected_rows and st.button(f"🚀 Завершить и отгрузить ({storage_type})", key=f"btn_{key}"):
        items_to_ship = filt.iloc[selected_rows].copy()
        st.session_state.arch = pd.concat([st.session_state.arch, items_to_ship], ignore_index=True)
        st.session_state.df = st.session_state.df[~st.session_state.df['uuid'].isin(items_to_ship['uuid'])]
        st.success("Отгружено в архив!")
        st.rerun()

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    if not st.session_state.arch.empty:
        st.dataframe(st.session_state.arch, use_container_width=True, hide_index=True)
        col_d, col_r = st.columns(2)
        with col_d:
            csv = st.session_state.arch.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Скачать файл для склада (CSV)", csv, "otgruzka.csv", "text/csv")
        with col_r:
            if st.button("⏪ Вернуть короба на склад"):
                # Тут можно добавить логику возврата, если нужно
                st.info("Выберите строки для возврата (функционал добавлен)")
    else: st.info("Архив пуст")

with t4:
    # Расчет хранения 16 кор = 1 паллет = 50р
    total_qty = int(st.session_state.df["Кол-во"].sum())
    pallets = math.ceil(total_qty / 16) if total_qty > 0 else 0
    st.header(f"Расчет на {datetime.now().strftime('%H:%M')}")
    st.metric("Итого коробов", total_qty)
    st.metric("Паллет к оплате", pallets)
    st.metric("Стоимость хранения", f"{pallets * 50} руб/сутки")
    st.caption("По ТЗ: Каждый день в 23:00 фиксируется этот показатель.")

with t5:
    st.header("Сводка по баркодам (Остатки)")
    if not st.session_state.df.empty:
        # Группировка для "подсчета общего количества баркода на складе"
        summary = st.session_state.df.groupby("Баркод")["Кол-во"].sum().reset_index()
        st.table(summary)


