        col1.bar_chart(df.groupby('Osoba')['Paczki'].sum(), color="#0078d4")
        
        col2.dataframe(
            final_stats,
            column_config={
                "Paczki Razem": st.column_config.ProgressColumn("Paczki", format="%d", max_value=int(final_stats['Paczki Razem'].max()) if not final_stats.empty else 100),
                "Błędy (System/Noc)": st.column_config.NumberColumn("Błędy", format="%d 🛑", help="Duplikaty lub poza godz. 05:00-18:00"),
                "Postój (10-30m)": st.column_config.NumberColumn("Postój", format="%d ⏳", help="Paczki po postoju 10-30m (nie wliczane do średniej)."),
                "Długie Przerwy": st.column_config.NumberColumn("Przerwy >30m", format="%d ☕"),
                "Wydajnosc": st.column_config.NumberColumn("Wydajność/h", format="%.1f"),
                "Godziny": st.column_config.NumberColumn("Czas Netto", format="%.1f h"),
                "Paczki Średnia": st.column_config.NumberColumn("Baza Średniej", format="%d")
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.write("### 🕵️‍♂️ Szczegóły dnia")
        st.dataframe(
            df_stats.sort_values(['Data', 'Osoba'], ascending=False),
            column_config={
                "Data": st.column_config.DateColumn("Data"),
                "Godziny": st.column_config.NumberColumn("Godziny", format="%.2f h"),
                "Błędy (System/Noc)": st.column_config.NumberColumn("Błędy/Noc", format="%d")
            },
            use_container_width=True
        )

    with tab2:
        st.subheader("📦 Oryginalny Raport Kartonów")
        kartony = df.groupby('Karton')['Paczki'].sum().reset_index().sort_values('Paczki', ascending=False)
        c_k1, c_k2 = st.columns([2, 1])
        c_k1.bar_chart(kartony.set_index('Karton'), color="#0078d4")
        c_k2.dataframe(kartony, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.subheader("📦 Kartony Niemieckie")

        from decimal import Decimal, InvalidOperation

        def waga_zamowienia(order):
            """Suma wag wszystkich produktów: waga sztuki w kg × ilość."""
            produkty = order.get("products")
            if not isinstance(produkty, list) or not produkty:
                return None
            suma = Decimal("0")
            try:
                for produkt in produkty:
                    waga = Decimal(str(produkt.get("weight", "")).strip().replace(",", "."))
                    ilosc = Decimal(str(produkt.get("quantity", "")).strip().replace(",", "."))
                    if (not waga.is_finite() or not ilosc.is_finite()
                            or waga <= 0 or ilosc <= 0):
                        return None
                    suma += waga * ilosc
            except (InvalidOperation, TypeError, ValueError, AttributeError):
                return None
            return suma

        # Oznaczenie, minimalna i maksymalna waga w kg,
        # liczba kartonów: 1x5DE, 2x5DE, 4x5DE.
        reguly_de = [
            ("1(5L)", Decimal("0"),    Decimal("5"),  (1, 0, 0)),
            ("1(5L)", Decimal("5.1"),  Decimal("10"), (0, 1, 0)),
            ("1(5L)", Decimal("10.1"), Decimal("20"), (0, 0, 1)),
            ("2(5L)", Decimal("20.1"), Decimal("30"), (0, 1, 1)),
            ("2(5L)", Decimal("30.1"), Decimal("40"), (0, 0, 2)),
            ("3(5L)", Decimal("40.1"), Decimal("50"), (0, 1, 2)),
            ("3(5L)", Decimal("50.1"), Decimal("60"), (0, 0, 3)),
        ]
        licznik_de = {"1x5DE": 0, "2x5DE": 0, "4x5DE": 0}
        wzor_oznaczenia = re.compile(r"(?<!\w)(\d+\(5L\))(?!\w)")

        for order in df_5de_filtered.to_dict("records"):
            wpis = str(order.get("extra_field_1") or "")
            oznaczenia = wzor_oznaczenia.findall(wpis)
            if len(oznaczenia) != 1:
                continue
            oznaczenie = oznaczenia[0]
            waga = waga_zamowienia(order)
            if waga is None:
                continue
            for marker, minimum, maksimum, kartony in reguly_de:
                if marker == oznaczenie and minimum <= waga <= maksimum:
                    licznik_de["1x5DE"] += kartony[0]
                    licznik_de["2x5DE"] += kartony[1]
                    licznik_de["4x5DE"] += kartony[2]
                    break
            # Wszystko poza powyższymi regułami jest pomijane.

        df_de_summary = pd.DataFrame([
            {"Karton (Status 136559)": rodzaj, "Ilość": ilosc}
            for rodzaj, ilosc in licznik_de.items()
        ]).sort_values("Ilość", ascending=False)

        c_de1, c_de2 = st.columns([2, 1])
        c_de1.bar_chart(
            df_de_summary.set_index("Karton (Status 136559)"),
            color="#2ecc71",
        )
        c_de2.dataframe(
            df_de_summary,
            hide_index=True,
            use_container_width=True,
        )

else:
    st.info("Brak danych do wyświetlenia. Odśwież API lub zmień filtry.")
