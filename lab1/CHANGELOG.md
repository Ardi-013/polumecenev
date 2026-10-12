# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-12

### Added
- Акустический DTMF-модем для передачи данных между ноутбуками через микрофон и динамики.
- Детектирование частот на базе алгоритма Гёрцеля со скользящим окном 60 мс (шаг 20 мс) и кадрированием (`*` и `#`).
- Диалоговое окно выбора файла для отправки изображения через системный файловый проводник.
- Каталог из 12 небесных тел Outer Wilds со скриншотами.
- Автоматическое распознавание отправленного файла по имени и сопоставление с каталогом.
- Фоновые потоки `QThread` для неблокирующей передачи и непрерывного приёма аудио.
