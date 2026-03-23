with open('ui/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

original = content

n1 = content.count('bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(0, 8))')
content = content.replace(
    'bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(0, 8))',
    'bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 8))'
)

n2 = content.count('pack(fill="both", expand=True, padx=16, pady=(16, 12))')
content = content.replace(
    'pack(fill="both", expand=True, padx=16, pady=(16, 12))',
    'pack(fill="both", expand=True, padx=16, pady=(8, 12))'
)

n3 = content.count('padx=0, pady=(0, 10))')
content = content.replace('padx=0, pady=(0, 10))', 'padx=0, pady=(0, 16))')

n4a = content.count('self._preview_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 0))')
content = content.replace(
    'self._preview_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 0))',
    'self._preview_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 0))'
)

n4b = content.count('self._lbl_audio_count.grid(row=1, column=0, sticky="w", padx=4, pady=(6, 0))')
content = content.replace(
    'self._lbl_audio_count.grid(row=1, column=0, sticky="w", padx=4, pady=(6, 0))',
    'self._lbl_audio_count.grid(row=1, column=0, sticky="w", padx=16, pady=(6, 0))'
)

n4c = content.count('_logs_hdr.grid(row=2, column=0, sticky="ew", padx=4, pady=(8, 2))')
content = content.replace(
    '_logs_hdr.grid(row=2, column=0, sticky="ew", padx=4, pady=(8, 2))',
    '_logs_hdr.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 2))'
)

n4d = content.count('self._log_text.grid(row=3, column=0, sticky="nsew", padx=0, pady=(0, 6))')
content = content.replace(
    'self._log_text.grid(row=3, column=0, sticky="nsew", padx=0, pady=(0, 6))',
    'self._log_text.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 6))'
)

n4e = content.count('self._lbl_progress_global.grid(row=4, column=0, sticky="w", padx=4)')
content = content.replace(
    'self._lbl_progress_global.grid(row=4, column=0, sticky="w", padx=4)',
    'self._lbl_progress_global.grid(row=4, column=0, sticky="w", padx=16)'
)

n4f = content.count('self._progress_global.grid(row=5, column=0, sticky="ew", padx=0, pady=(2, 2))')
content = content.replace(
    'self._progress_global.grid(row=5, column=0, sticky="ew", padx=0, pady=(2, 2))',
    'self._progress_global.grid(row=5, column=0, sticky="ew", padx=16, pady=(2, 2))'
)

n4g = content.count('self._lbl_progress_file.grid(row=6, column=0, sticky="w", padx=4)')
content = content.replace(
    'self._lbl_progress_file.grid(row=6, column=0, sticky="w", padx=4)',
    'self._lbl_progress_file.grid(row=6, column=0, sticky="w", padx=16)'
)

n4h = content.count('self._progress_file.grid(row=7, column=0, sticky="ew", padx=0, pady=(0, 0))')
content = content.replace(
    'self._progress_file.grid(row=7, column=0, sticky="ew", padx=0, pady=(0, 0))',
    'self._progress_file.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 0))'
)

print(f"bar.grid matches:         {n1}")
print(f"scrollable pack matches:  {n2}")
print(f"inter-card (0,10):        {n3}")
print(f"preview_frame:            {n4a}")
print(f"lbl_audio_count:          {n4b}")
print(f"_logs_hdr:                {n4c}")
print(f"log_text:                 {n4d}")
print(f"lbl_progress_global:      {n4e}")
print(f"progress_global:          {n4f}")
print(f"lbl_progress_file:        {n4g}")
print(f"progress_file:            {n4h}")

if content != original:
    with open('ui/app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("File written OK")
else:
    print("WARNING: no changes made")
