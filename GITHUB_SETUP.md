# Subir a GitHub

El repositorio ya incluye `.gitignore` y un workflow de GitHub Actions para compilar Windows.

```powershell
git init
git add .
git commit -m "Product Intelligence V9"
git branch -M main
git remote add origin TU_URL_GITHUB
git push -u origin main
```

No subas API keys. La GUI no necesita guardar la key en archivos; se introduce al ejecutar. Los Excel locales dentro de `excel/`, salidas, entornos virtuales, Chromium, `build/` y `dist/` están ignorados.

Para compilar en GitHub: **Actions → Build Windows EXE → Run workflow**. El resultado aparece como artifact `ProductIntelligence-Windows`.
