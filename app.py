if idx:
            c1, c2 = st.columns(2)
            
            # НОВАЯ ЛОГИКА ДЛЯ ОТГРУЗКИ ИП С ВЫГРУЗКОЙ EXCEL
            if c1.button(f"🚀 Отгрузить и скачать ({len(idx)})", key=f"ship_btn_{key}"):
                selected_rows = df.iloc[idx].copy()
                
                # 1. Формируем Excel файл в памяти
                output = io.BytesIO()
                export_df = selected_rows[['barcode', 'quantity', 'box_num']].copy()
                export_df.columns = ["Баркод", "Кол-во", "Номер короба"]
                export_df["Дата отгрузки"] = datetime.now().strftime("%d.%m.%Y")
                
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, index=False)
                
                # Сохраняем файл в сессию, чтобы кнопка скачивания появилась
                st.session_state[f"temp_file_{key}"] = output.getvalue()
                
                # 2. Переносим данные в архив базы данных
                with engine.connect() as conn:
                    for _, r in selected_rows.iterrows():
                        conn.execute(text("INSERT INTO archive SELECT *, :d FROM stock WHERE uuid=:u"), 
                                    {"d": datetime.now().strftime("%d.%m %H:%M"), "u": r['uuid']})
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": r['uuid']})
                    conn.commit()
                
                st.success(f"Готово! Данные {storage_type} в архиве. Нажмите 'Скачать файл' ниже.")

            # Показываем кнопку скачивания, если отгрузка была нажата
            if f"temp_file_{key}" in st.session_state:
                st.download_button(
                    label="📥 СКАЧАТЬ ЛИСТ ОТГРУЗКИ",
                    data=st.session_state[f"temp_file_{key}"],
                    file_name=f"otgruzka_{storage_type}_{datetime.now().strftime('%d_%m')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click=lambda: st.session_state.pop(f"temp_file_{key}", None) or reset_selection()
                )

            if c2.button(f"🗑️ Удалить ({len(idx)})", key=f"del_btn_{key}"):
                with engine.connect() as conn:
                    for i in idx:
                        conn.execute(text("DELETE FROM stock WHERE uuid=:u"), {"u": df.iloc[i]['uuid']})
                    conn.commit()
                reset_selection()
                st.rerun()
    else: st.info(f"Склад {storage_type} пуст")

with t1: render_table("ИП", "ip")
with t2: render_table("ООО", "ooo")

with t3:
    arch_type = st.radio("Архив:", ["ИП", "ООО"], horizontal=True, key="arch_sel")
    df_arch = pd.read_sql(text(f"SELECT * FROM archive WHERE type='{arch_type}'"), engine)
    
    if not df_arch.empty:
        arch_table_key = f"arch_table_{arch_type}_{st.session_state.reset_counter}"
        sel_a = st.dataframe(df_arch, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=arch_table_key)
        
        export_df = df_arch[['barcode', 'quantity', 'box_num', 'ship_date']].copy()
        export_df.columns = ["Баркод", "Кол-во", "Номер короба", "Дата приемки"]
        export_df["ФИО сотрудника"] = ""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Архив')
        st.download_button(f"📥 Скачать архив {arch_type}", output.getvalue(), f"archive_{arch_type}.xlsx")

        idx_a = sel_a.get("selection", {}).get("rows", [])
        if idx_a:
            ca1, ca2 = st.columns(2)
            if ca1.button(f"🔙 Вернуть на баланс ({len(idx_a)})", key=f"res_btn_{arch_type}"):
                with engine.connect() as conn:
                    for i in idx_a:
                        r = df_arch.iloc[i]
                        conn.execute(text("INSERT INTO stock SELECT uuid, name, article, barcode, quantity, box_num, type FROM archive WHERE uuid=:u"), {"u": r['uuid']})
                        conn.execute(text("DELETE FROM archive WHERE uuid=:u"), {"u": r['uuid']})
                    conn.commit()
                reset_selection()
                st.rerun()
            if ca2.button(f"🔥 Очистить архив ({len(idx_a)})", key=f"clear_btn_{arch_type}"):
                with engine.connect() as conn:
                    for i in idx_a:
                        conn.execute(text("DELETE FROM archive WHERE uuid=:u"), {"u": df_arch.iloc[i]['uuid']})
                    conn.commit()
                reset_selection()
                st.rerun()
    else: st.info("Архив пуст")

with t4:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    boxes = len(df_all)
    pallets = math.ceil(boxes / 16) if boxes > 0 else 0
    st.metric("Коробов", boxes)
    st.metric("Паллет", pallets)
    st.write(f"Стоимость: {pallets * 50} ₽/сут")

with t5:
    df_all = pd.read_sql(text("SELECT * FROM stock"), engine)
    if not df_all.empty:
        res = df_all.groupby(["type", "barcode"])["quantity"].sum().reset_index()
        res.columns = ["Тип", "Баркод", "Общее количество"]
        st.dataframe(res, use_container_width=True, hide_index=True)

