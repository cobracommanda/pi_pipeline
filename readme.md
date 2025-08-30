python process_excel_files.py -i excel -o outputs --pretty
node extractLessonBlocks.js --dir data/pre_processed --out level_3_units
python sheets.py --meta units.json --from_dir outputs
python attach_pages.py --meta units.json --blocks_dir level_3_units --levels 3,4 --units 1-30 --pages 1,2,3 --backup
python return_html.py
python add_audio_tags.py
python workbook_to_xml.py -i /Users/DRobinson/Desktop/phonic_intervention/level_3.json -o level_3_xml_output

python generate_all_navs.py level_3_xml_output
python pour_them_all.py --units 1-30