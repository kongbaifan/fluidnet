
(() => {
'use strict';
const ICONS = {"Activity":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-activity\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2\"></path></svg>","ArrowDownToLine":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-down-to-line\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 17V3\"></path><path d=\"m6 11 6 6 6-6\"></path><path d=\"M19 21H5\"></path></svg>","ArrowRight":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-right\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 12h14\"></path><path d=\"m12 5 7 7-7 7\"></path></svg>","ArrowRightLeft":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-right-left\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m16 3 4 4-4 4\"></path><path d=\"M20 7H4\"></path><path d=\"m8 21-4-4 4-4\"></path><path d=\"M4 17h16\"></path></svg>","ArrowUpRight":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-up-right\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M7 7h10v10\"></path><path d=\"M7 17 17 7\"></path></svg>","Bell":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-bell\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M10.268 21a2 2 0 0 0 3.464 0\"></path><path d=\"M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326\"></path></svg>","BookOpen":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-book-open\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 7v14\"></path><path d=\"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z\"></path></svg>","Box":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-box\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z\"></path><path d=\"m3.3 7 8.7 5 8.7-5\"></path><path d=\"M12 22V12\"></path></svg>","Boxes":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-boxes\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z\"></path><path d=\"m7 16.5-4.74-2.85\"></path><path d=\"m7 16.5 5-3\"></path><path d=\"M7 16.5v5.17\"></path><path d=\"M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z\"></path><path d=\"m17 16.5-5-3\"></path><path d=\"m17 16.5 4.74-2.85\"></path><path d=\"M17 16.5v5.17\"></path><path d=\"M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z\"></path><path d=\"M12 8 7.26 5.15\"></path><path d=\"m12 8 4.74-2.85\"></path><path d=\"M12 13.5V8\"></path></svg>","Braces":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-braces\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1\"></path><path d=\"M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1\"></path></svg>","Cable":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-cable\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M17 21v-2a1 1 0 0 1-1-1v-1a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1a1 1 0 0 1-1 1\"></path><path d=\"M19 15V6.5a1 1 0 0 0-7 0v11a1 1 0 0 1-7 0V9\"></path><path d=\"M21 21v-2h-4\"></path><path d=\"M3 5h4V3\"></path><path d=\"M7 5a1 1 0 0 1 1 1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1V3\"></path></svg>","Check":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-check\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 6 9 17l-5-5\"></path></svg>","CheckCheck":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-check-check\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M18 6 7 17l-5-5\"></path><path d=\"m22 10-7.5 7.5L13 16\"></path></svg>","CheckCircle2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-check\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"m9 12 2 2 4-4\"></path></svg>","ChevronDown":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-chevron-down\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m6 9 6 6 6-6\"></path></svg>","ChevronLeft":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-chevron-left\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m15 18-6-6 6-6\"></path></svg>","ChevronRight":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-chevron-right\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m9 18 6-6-6-6\"></path></svg>","Circle":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle></svg>","CircleDot":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-dot\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><circle cx=\"12\" cy=\"12\" r=\"1\"></circle></svg>","CircleHelp":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-help\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3\"></path><path d=\"M12 17h.01\"></path></svg>","CirclePlus":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-plus\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"M8 12h8\"></path><path d=\"M12 8v8\"></path></svg>","Clipboard":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-clipboard\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"8\" height=\"4\" x=\"8\" y=\"2\" rx=\"1\" ry=\"1\"></rect><path d=\"M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2\"></path></svg>","Clock3":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-clock3\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><polyline points=\"12 6 12 12 16.5 12\"></polyline></svg>","Code2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-code-xml\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m18 16 4-4-4-4\"></path><path d=\"m6 8-4 4 4 4\"></path><path d=\"m14.5 4-5 16\"></path></svg>","Columns2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-columns2\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect><path d=\"M12 3v18\"></path></svg>","Copy":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-copy\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"14\" height=\"14\" x=\"8\" y=\"8\" rx=\"2\" ry=\"2\"></rect><path d=\"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2\"></path></svg>","Database":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-database\" aria-hidden=\"true\" focusable=\"false\"><ellipse cx=\"12\" cy=\"5\" rx=\"9\" ry=\"3\"></ellipse><path d=\"M3 5V19A9 3 0 0 0 21 19V5\"></path><path d=\"M3 12A9 3 0 0 0 21 12\"></path></svg>","Download":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-download\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"></path><polyline points=\"7 10 12 15 17 10\"></polyline><line x1=\"12\" x2=\"12\" y1=\"15\" y2=\"3\"></line></svg>","Droplets":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-droplets\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z\"></path><path d=\"M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97\"></path></svg>","Ellipsis":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-ellipsis\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"1\"></circle><circle cx=\"19\" cy=\"12\" r=\"1\"></circle><circle cx=\"5\" cy=\"12\" r=\"1\"></circle></svg>","ExternalLink":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-external-link\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 3h6v6\"></path><path d=\"M10 14 21 3\"></path><path d=\"M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6\"></path></svg>","Eye":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-eye\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0\"></path><circle cx=\"12\" cy=\"12\" r=\"3\"></circle></svg>","FileCode2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-file-code2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4\"></path><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"></path><path d=\"m5 12-3 3 3 3\"></path><path d=\"m9 18 3-3-3-3\"></path></svg>","FileJson":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-file-json\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\"></path><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"></path><path d=\"M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1\"></path><path d=\"M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1\"></path></svg>","FileText":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-file-text\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\"></path><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"></path><path d=\"M10 9H8\"></path><path d=\"M16 13H8\"></path><path d=\"M16 17H8\"></path></svg>","Filter":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-filter\" aria-hidden=\"true\" focusable=\"false\"><polygon points=\"22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3\"></polygon></svg>","Flame":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-flame\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z\"></path></svg>","Folder":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-folder\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\"></path></svg>","FolderOpen":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-folder-open\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2\"></path></svg>","Gauge":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-gauge\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m12 14 4-4\"></path><path d=\"M3.34 19a10 10 0 1 1 17.32 0\"></path></svg>","GitBranch":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-git-branch\" aria-hidden=\"true\" focusable=\"false\"><line x1=\"6\" x2=\"6\" y1=\"3\" y2=\"15\"></line><circle cx=\"18\" cy=\"6\" r=\"3\"></circle><circle cx=\"6\" cy=\"18\" r=\"3\"></circle><path d=\"M18 9a9 9 0 0 1-9 9\"></path></svg>","GitCompareArrows":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-git-compare-arrows\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"5\" cy=\"6\" r=\"3\"></circle><path d=\"M12 6h5a2 2 0 0 1 2 2v7\"></path><path d=\"m15 9-3-3 3-3\"></path><circle cx=\"19\" cy=\"18\" r=\"3\"></circle><path d=\"M12 18H7a2 2 0 0 1-2-2V9\"></path><path d=\"m9 15 3 3-3 3\"></path></svg>","Grid2X2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-grid2x2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 3v18\"></path><path d=\"M3 12h18\"></path><rect x=\"3\" y=\"3\" width=\"18\" height=\"18\" rx=\"2\"></rect></svg>","Grip":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-grip\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"5\" r=\"1\"></circle><circle cx=\"19\" cy=\"5\" r=\"1\"></circle><circle cx=\"5\" cy=\"5\" r=\"1\"></circle><circle cx=\"12\" cy=\"12\" r=\"1\"></circle><circle cx=\"19\" cy=\"12\" r=\"1\"></circle><circle cx=\"5\" cy=\"12\" r=\"1\"></circle><circle cx=\"12\" cy=\"19\" r=\"1\"></circle><circle cx=\"19\" cy=\"19\" r=\"1\"></circle><circle cx=\"5\" cy=\"19\" r=\"1\"></circle></svg>","GripVertical":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-grip-vertical\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"9\" cy=\"12\" r=\"1\"></circle><circle cx=\"9\" cy=\"5\" r=\"1\"></circle><circle cx=\"9\" cy=\"19\" r=\"1\"></circle><circle cx=\"15\" cy=\"12\" r=\"1\"></circle><circle cx=\"15\" cy=\"5\" r=\"1\"></circle><circle cx=\"15\" cy=\"19\" r=\"1\"></circle></svg>","History":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-history\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\"></path><path d=\"M3 3v5h5\"></path><path d=\"M12 7v5l4 2\"></path></svg>","Home":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-house\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8\"></path><path d=\"M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\"></path></svg>","Info":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-info\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"M12 16v-4\"></path><path d=\"M12 8h.01\"></path></svg>","Keyboard":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-keyboard\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M10 8h.01\"></path><path d=\"M12 12h.01\"></path><path d=\"M14 8h.01\"></path><path d=\"M16 12h.01\"></path><path d=\"M18 8h.01\"></path><path d=\"M6 8h.01\"></path><path d=\"M7 16h10\"></path><path d=\"M8 12h.01\"></path><rect width=\"20\" height=\"16\" x=\"2\" y=\"4\" rx=\"2\"></rect></svg>","Layers":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-layers\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z\"></path><path d=\"M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12\"></path><path d=\"M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17\"></path></svg>","LayoutDashboard":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-layout-dashboard\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"7\" height=\"9\" x=\"3\" y=\"3\" rx=\"1\"></rect><rect width=\"7\" height=\"5\" x=\"14\" y=\"3\" rx=\"1\"></rect><rect width=\"7\" height=\"9\" x=\"14\" y=\"12\" rx=\"1\"></rect><rect width=\"7\" height=\"5\" x=\"3\" y=\"16\" rx=\"1\"></rect></svg>","List":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-list\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12h.01\"></path><path d=\"M3 18h.01\"></path><path d=\"M3 6h.01\"></path><path d=\"M8 12h13\"></path><path d=\"M8 18h13\"></path><path d=\"M8 6h13\"></path></svg>","ListChecks":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-list-checks\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m3 17 2 2 4-4\"></path><path d=\"m3 7 2 2 4-4\"></path><path d=\"M13 6h8\"></path><path d=\"M13 12h8\"></path><path d=\"M13 18h8\"></path></svg>","Lock":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-lock\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"11\" x=\"3\" y=\"11\" rx=\"2\" ry=\"2\"></rect><path d=\"M7 11V7a5 5 0 0 1 10 0v4\"></path></svg>","Maximize2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-maximize2\" aria-hidden=\"true\" focusable=\"false\"><polyline points=\"15 3 21 3 21 9\"></polyline><polyline points=\"9 21 3 21 3 15\"></polyline><line x1=\"21\" x2=\"14\" y1=\"3\" y2=\"10\"></line><line x1=\"3\" x2=\"10\" y1=\"21\" y2=\"14\"></line></svg>","MessageSquare":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-message-square\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z\"></path></svg>","Minimize2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-minimize2\" aria-hidden=\"true\" focusable=\"false\"><polyline points=\"4 14 10 14 10 20\"></polyline><polyline points=\"20 10 14 10 14 4\"></polyline><line x1=\"14\" x2=\"21\" y1=\"10\" y2=\"3\"></line><line x1=\"3\" x2=\"10\" y1=\"21\" y2=\"14\"></line></svg>","Minus":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-minus\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 12h14\"></path></svg>","Monitor":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-monitor\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"20\" height=\"14\" x=\"2\" y=\"3\" rx=\"2\"></rect><line x1=\"8\" x2=\"16\" y1=\"21\" y2=\"21\"></line><line x1=\"12\" x2=\"12\" y1=\"17\" y2=\"21\"></line></svg>","Moon":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-moon\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z\"></path></svg>","MoreHorizontal":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-ellipsis\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"1\"></circle><circle cx=\"19\" cy=\"12\" r=\"1\"></circle><circle cx=\"5\" cy=\"12\" r=\"1\"></circle></svg>","MousePointer2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-mouse-pointer2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.063z\"></path></svg>","Move":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-move\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 2v20\"></path><path d=\"m15 19-3 3-3-3\"></path><path d=\"m19 9 3 3-3 3\"></path><path d=\"M2 12h20\"></path><path d=\"m5 9-3 3 3 3\"></path><path d=\"m9 5 3-3 3 3\"></path></svg>","Network":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-network\" aria-hidden=\"true\" focusable=\"false\"><rect x=\"16\" y=\"16\" width=\"6\" height=\"6\" rx=\"1\"></rect><rect x=\"2\" y=\"16\" width=\"6\" height=\"6\" rx=\"1\"></rect><rect x=\"9\" y=\"2\" width=\"6\" height=\"6\" rx=\"1\"></rect><path d=\"M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3\"></path><path d=\"M12 12V8\"></path></svg>","PanelLeftClose":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-panel-left-close\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect><path d=\"M9 3v18\"></path><path d=\"m16 15-3-3 3-3\"></path></svg>","PanelLeftOpen":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-panel-left-open\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect><path d=\"M9 3v18\"></path><path d=\"m14 9 3 3-3 3\"></path></svg>","Pause":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-pause\" aria-hidden=\"true\" focusable=\"false\"><rect x=\"14\" y=\"4\" width=\"4\" height=\"16\" rx=\"1\"></rect><rect x=\"6\" y=\"4\" width=\"4\" height=\"16\" rx=\"1\"></rect></svg>","Pencil":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-pencil\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z\"></path><path d=\"m15 5 4 4\"></path></svg>","Pin":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-pin\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 17v5\"></path><path d=\"M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z\"></path></svg>","Play":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-play\" aria-hidden=\"true\" focusable=\"false\"><polygon points=\"6 3 20 12 6 21 6 3\"></polygon></svg>","Plug":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-plug\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 22v-5\"></path><path d=\"M9 8V2\"></path><path d=\"M15 8V2\"></path><path d=\"M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z\"></path></svg>","Plus":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-plus\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 12h14\"></path><path d=\"M12 5v14\"></path></svg>","Redo2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-redo2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m15 14 5-5-5-5\"></path><path d=\"M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13\"></path></svg>","RefreshCw":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-refresh-cw\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8\"></path><path d=\"M21 3v5h-5\"></path><path d=\"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16\"></path><path d=\"M8 16H3v5\"></path></svg>","RotateCcw":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-rotate-ccw\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\"></path><path d=\"M3 3v5h5\"></path></svg>","RotateCw":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-rotate-cw\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8\"></path><path d=\"M21 3v5h-5\"></path></svg>","Save":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-save\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z\"></path><path d=\"M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7\"></path><path d=\"M7 3v4a1 1 0 0 0 1 1h7\"></path></svg>","Scan":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-scan\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 7V5a2 2 0 0 1 2-2h2\"></path><path d=\"M17 3h2a2 2 0 0 1 2 2v2\"></path><path d=\"M21 17v2a2 2 0 0 1-2 2h-2\"></path><path d=\"M7 21H5a2 2 0 0 1-2-2v-2\"></path></svg>","Search":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-search\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"11\" cy=\"11\" r=\"8\"></circle><path d=\"m21 21-4.3-4.3\"></path></svg>","Settings2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-settings2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 7h-9\"></path><path d=\"M14 17H5\"></path><circle cx=\"17\" cy=\"17\" r=\"3\"></circle><circle cx=\"7\" cy=\"7\" r=\"3\"></circle></svg>","ShieldCheck":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-shield-check\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z\"></path><path d=\"m9 12 2 2 4-4\"></path></svg>","SlidersHorizontal":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-sliders-horizontal\" aria-hidden=\"true\" focusable=\"false\"><line x1=\"21\" x2=\"14\" y1=\"4\" y2=\"4\"></line><line x1=\"10\" x2=\"3\" y1=\"4\" y2=\"4\"></line><line x1=\"21\" x2=\"12\" y1=\"12\" y2=\"12\"></line><line x1=\"8\" x2=\"3\" y1=\"12\" y2=\"12\"></line><line x1=\"21\" x2=\"16\" y1=\"20\" y2=\"20\"></line><line x1=\"12\" x2=\"3\" y1=\"20\" y2=\"20\"></line><line x1=\"14\" x2=\"14\" y1=\"2\" y2=\"6\"></line><line x1=\"8\" x2=\"8\" y1=\"10\" y2=\"14\"></line><line x1=\"16\" x2=\"16\" y1=\"18\" y2=\"22\"></line></svg>","Square":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-square\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect></svg>","SquareDashed":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-square-dashed\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 3a2 2 0 0 0-2 2\"></path><path d=\"M19 3a2 2 0 0 1 2 2\"></path><path d=\"M21 19a2 2 0 0 1-2 2\"></path><path d=\"M5 21a2 2 0 0 1-2-2\"></path><path d=\"M9 3h1\"></path><path d=\"M9 21h1\"></path><path d=\"M14 3h1\"></path><path d=\"M14 21h1\"></path><path d=\"M3 9v1\"></path><path d=\"M21 9v1\"></path><path d=\"M3 14v1\"></path><path d=\"M21 14v1\"></path></svg>","Star":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-star\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z\"></path></svg>","StepForward":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-step-forward\" aria-hidden=\"true\" focusable=\"false\"><line x1=\"6\" x2=\"6\" y1=\"4\" y2=\"20\"></line><polygon points=\"10,4 20,12 10,20\"></polygon></svg>","Sun":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-sun\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"4\"></circle><path d=\"M12 2v2\"></path><path d=\"M12 20v2\"></path><path d=\"m4.93 4.93 1.41 1.41\"></path><path d=\"m17.66 17.66 1.41 1.41\"></path><path d=\"M2 12h2\"></path><path d=\"M20 12h2\"></path><path d=\"m6.34 17.66-1.41 1.41\"></path><path d=\"m19.07 4.93-1.41 1.41\"></path></svg>","Table2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-table2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18\"></path></svg>","Terminal":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-terminal\" aria-hidden=\"true\" focusable=\"false\"><polyline points=\"4 17 10 11 4 5\"></polyline><line x1=\"12\" x2=\"20\" y1=\"19\" y2=\"19\"></line></svg>","Thermometer":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-thermometer\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z\"></path></svg>","Trash2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-trash2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 6h18\"></path><path d=\"M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6\"></path><path d=\"M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2\"></path><line x1=\"10\" x2=\"10\" y1=\"11\" y2=\"17\"></line><line x1=\"14\" x2=\"14\" y1=\"11\" y2=\"17\"></line></svg>","Triangle":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-triangle\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M13.73 4a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z\"></path></svg>","Undo2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-undo2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M9 14 4 9l5-5\"></path><path d=\"M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11\"></path></svg>","Upload":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-upload\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"></path><polyline points=\"17 8 12 3 7 8\"></polyline><line x1=\"12\" x2=\"12\" y1=\"3\" y2=\"15\"></line></svg>","Waypoints":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-waypoints\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"4.5\" r=\"2.5\"></circle><path d=\"m10.2 6.3-3.9 3.9\"></path><circle cx=\"4.5\" cy=\"12\" r=\"2.5\"></circle><path d=\"M7 12h10\"></path><circle cx=\"19.5\" cy=\"12\" r=\"2.5\"></circle><path d=\"m13.8 17.7 3.9-3.9\"></path><circle cx=\"12\" cy=\"19.5\" r=\"2.5\"></circle></svg>","Wind":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-wind\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12.8 19.6A2 2 0 1 0 14 16H2\"></path><path d=\"M17.5 8a2.5 2.5 0 1 1 2 4H2\"></path><path d=\"M9.8 4.4A2 2 0 1 1 11 8H2\"></path></svg>","Wrench":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-wrench\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z\"></path></svg>","X":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-x\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M18 6 6 18\"></path><path d=\"m6 6 12 12\"></path></svg>","Zap":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-zap\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z\"></path></svg>"};
// 模块编辑采用 Python；source.header 保留为旧存档中的公共代码字段。
function pythonModuleSource(kind, code) {
  return {
    runtime: kind === 'valve'
      ? `# ${code} · 运行函数\n# 参数与端口由模块定义提供\n\ndef run():\n    # 读取当前已生效的设备参数\n    opening = OPENING / 100.0\n\n    # 在此描述设备关系，供全网求解使用\n    return {"opening_ratio": opening}\n`
      : `# ${code} · 运行函数\ndef run():\n    # 在此编辑设备算法\n    pass\n`,
    header: `# ${code} · 公共代码\nfrom dataclasses import dataclass\n\n\n@dataclass\nclass PortState:\n    pressure: float = 0.201325  # MPa\n    temperature: float = 20.0  # °C\n    density: float = 998.2  # kg/m³\n`,
    design: [80, 65, 40].map((opening, i) => kind === 'valve'
      ? `# 库值 ${i + 1} · ${['额定工况', '部分负荷', '调试备份'][i]}\ndef design${i + 1}():\n    return {"OPENING": ${opening}.0, "KV": 16.0}\n`
      : `# ${code} · 库值 ${i + 1}\ndef design${i + 1}():\n    # 返回此方案的设计参数\n    return {}\n`)
  };
}
function legacyModuleSource(kind, code) {
  return {
    runtime: kind === 'valve'
      ? `// ${code} · 运行函数\n// 参数与端口由模块定义提供\n\nvoid Run() {\n  // 读取已接受的端口状态\n  double opening = OPENING / 100.0;\n\n  // 提供设备关系，由全网统一求解\n  // 运行代码在本原型中仅作编辑预览\n}\n`
      : `// ${code} · 运行函数\nvoid Run() {\n  // 在此编辑设备算法\n  // 当前原型不编译或执行代码\n}\n`,
    header: `#pragma once\n\n// ${code} · 公共声明\nstruct PortState {\n  double pressure;    // Pa\n  double temperature; // K\n  double density;     // kg/m³\n};\n`,
    design: [80, 65, 40].map((opening, i) => kind === 'valve'
      ? `// 库值 ${i + 1} · ${['额定工况', '部分负荷', '调试备份'][i]}\nvoid Design${i + 1}() {\n  OPENING = ${opening}.0;\n  KV = 16.0;\n}\n`
      : `// ${code} · 库值 ${i + 1}\nvoid Design${i + 1}() {\n  // 编辑设计参数\n}\n`)
  };
}
function normalizePythonSource(m) {
  if (m.runtime === 'python' || m.sourceFormat === 'python-v1') return;
  const next = pythonModuleSource(m.kind, m.code);
  const candidates = [m.code, MODULE_SPECS.find(spec => spec[0] === m.kind)?.[2]].filter(Boolean).map(code => legacyModuleSource(m.kind, code));
  const same = (a, b) => typeof a === 'string' && a.replace(/\r\n/g, '\n') === b;
  for (const key of ['runtime', 'header']) if (candidates.some(old => same(m.source[key], old[key]))) m.source[key] = next[key];
  m.source.design = m.source.design.map((source, i) => candidates.some(old => same(source, old.design[i])) ? next.design[i] : source);
  m.sourceFormat = 'python-v1';
}
// 浏览器仅做轻量结构检查：忽略 Python 注释与字符串中的括号，不执行代码。
function pythonCodeIssue(source) {
  const stack = [], pairs = { ')': '(', ']': '[', '}': '{' };
  let i = 0, line = 1, clean = '';
  while (i < source.length) {
    const c = source[i];
    if (c === '\n') { line++; clean += c; i++; continue; }
    if (c === '#') {
      while (i < source.length && source[i] !== '\n') i++;
      continue;
    }
    if (c === '"' || c === "'") {
      const startLine = line, quote = source.slice(i, i + 3) === c.repeat(3) ? c.repeat(3) : c;
      i += quote.length; clean += '0';
      let closed = false;
      while (i < source.length) {
        if (source.slice(i, i + quote.length) === quote) { i += quote.length; closed = true; break; }
        if (source[i] === '\\') { if (source[i + 1] === '\n') { line++; clean += '\n'; } i += 2; continue; }
        if (source[i] === '\n') { if (quote.length === 1) break; line++; clean += '\n'; }
        i++;
      }
      if (!closed) return `第 ${startLine} 行：字符串未闭合。`;
      continue;
    }
    if ('([{'.includes(c)) stack.push({ char: c, line });
    else if (pairs[c] && stack.pop()?.char !== pairs[c]) return `第 ${line} 行：括号不配对。`;
    clean += c; i++;
  }
  if (stack.length) return `第 ${stack.at(-1).line} 行：括号不配对。`;
  const legacyLine = clean.split('\n').findIndex(text => /^\s*(?:void\s+\w+\s*\(|struct\s+\w+|\/\/)/.test(text));
  if (legacyLine >= 0) return `第 ${legacyLine + 1} 行：检测到旧版代码写法，请改为 Python；已保留原文。`;
  return '';
}

const STORAGE_KEY = 'fluidnet-prototype-engine-v1';
let engine = null;
let workflows = null;
let scenarioBatches = {markup:()=>'',afterRender:()=>{},action:async()=>{}};
let coldStorage = {markup:()=>'',refresh:()=>{},action:async()=>{},couplingToolbar:()=>'',couplingReferences:()=>[],assertCouplingIdle:()=>{},syncCouplingCharts:()=>{},couplingChartBindings:()=>[]};
const UI_KEY = STORAGE_KEY + '-ui';
// 本地草稿写入 localStorage 的降级阶梯：配额不足时只在“用于存储的副本”上裁剪运行历史，
// 每级为 [每次运行保留的最近帧数, 保留的运行快照条数]；内存中的 state 不裁剪，用户仍可导出原型。
const LOCAL_DRAFT_STEPS = [[200, null], [200, 5], [200, 1], [50, 0]];
const PAGE_META = {
  home:['首页','Home','项目、模块与任务概览'],
  projects:['项目','FolderOpen','项目管理与示例'],
  workbench:['建模','Network','管网建模与设备调节'],
  modules:['模块','Boxes','模块库与开发入口'],
  editor:['模块开发','Box','图形、变量、代码与通路'],
  nodes:['节点定义','Waypoints','四类端口与连接约定'],
  bench:['验证台','CheckCheck','Python 模块独立验证与状态提交'],
  models:['型号','Database','设备型号与版本管理'],
  curves:['曲线','Activity','变量曲线与工况对照'],
  runs:['记录','History','运行记录、参数与导出'],
  batches:['批量','ListChecks','批量工况、结果存档与方案比较'],
  controls:['控制','Code2','控制逻辑与观察变量'],
  connections:['对接','Plug','变量接口、访问令牌与串口'],
  settings:['设置','Settings2','介质、求解与显示'],
  help:['指南','BookOpen','页面导览与使用流程']
};
const EDITOR_TABS = [['drawing','绘制模块','SquareDashed'],['attributes','变量属性','List'],['values','变量值','Table2'],['models','设备型号','Database'],['code','代码','Code2'],['channels','通路设置','Waypoints']];
const DOMAINS = { fluid:{label:'流体',color:'orange',unit:'kg/s',icon:'Droplets'}, thermal:{label:'传热',color:'blue',unit:'W',icon:'Thermometer'}, refrigerant:{label:'制冷剂',color:'green',unit:'kg/s',icon:'Droplets'}, info:{label:'信息',color:'green',unit:'—',icon:'Activity'}, power:{label:'电力',color:'purple',unit:'A',icon:'Zap'}, mech:{label:'机械',color:'blue',unit:'N·m',icon:'RotateCw'} };
// Port name prefixes for ports added in the module editor (station refrigerant ports are built-in only).
const PORT_PREFIX = { fluid: ['IM', 'EX'], info: ['II', 'IO'], power: ['PI', 'PO'], mech: ['MI', 'MO'] };
const PARAM_DEFS = {
  source:[['pressure','绝对压力','kPa',110,1000,1,201.325],['temperature','温度','°C',-100,400,1,20]],
  pump:[['speed','转速比','倍',.2,1.3,.05,1],['efficiency','泵效率','%',1,100,1,75]],
  valve:[['opening','阀门开度','%',0,100,1,80],['kv','流量系数 Kv','m³/h',.1,200,.5,16]],
  pipe:[['length','管道长度','m',.1,1000,.5,30],['diameter','管道内径','mm',5,1000,1,40],['heatLoss','散热能力 UA','W/K',0,10000,1,0],['ambient','环境温度','°C',-100,400,1,20],['cells','热容分段数（0 为无热惯性）','段',0,50,1,0],['wallHeat','管壁热容','kJ/K',0,10000,1,0]],
  junction:[['elevation','标高','m',-100,1000,.1,0]],
  tank:[['level','初始液位','m',0,20,.1,2],['area','横截面积','m²',.01,100,.1,2.5],['height','罐高（满箱液位）','m',.1,30,.1,5],['temperature','初始水温','°C',-100,400,1,20],['heater','加热功率','W',-1e6,1e6,100,0],['heatLoss','散热能力 UA','W/K',0,10000,1,0],['ambient','环境温度','°C',-100,400,1,20]],
  exchanger:[['ua','传热系数 UA','W/K',1,50000,100,2000],['loss','阻力系数','—',0,1000,.1,5]],
  heater:[['power','加热功率','kW',0,1000,1,20]],
  sensor:[['range','量程上限','kg/s',.1,1000,1,10]],
  pid:[['setpoint','目标值','°C',0,100,.1,45],['kp','比例增益','—',0,1000,.1,2]],
  refprop:[],
  check:[['loss','阻力系数','—',0,1000,.1,2]]
};
const MODULE_SPECS = [
  ['source','压力边界','BOUNDARY','边界与节点','Droplets','为回路提供压力与温度边界。'],
  ['junction','连接节点','JUNCTION','边界与节点','Waypoints','连接多条支路，表达节点守恒关系。'],
  ['tank','储水罐','TANK','边界与节点','Database','包含液位、容积和储能状态的设备。'],
  ['pipe','圆管','PIPE','管道与阻力','Minus','长度、内径与阻力参数共同定义管段。'],
  ['valve','调节阀','VALVE','管道与阻力','SlidersHorizontal','通过开度调节支路，支持型号参数复用。'],
  ['check','止回阀','CHECK','管道与阻力','ArrowRightLeft','单向流动元件与局部阻力参数。'],
  ['pump','离心泵','PUMP','流体机械','Triangle','泵转速与性能参数的可调设备。'],
  ['exchanger','双侧换热器','HEAT_EXCHANGER','热力设备','ArrowRightLeft','两个独立流体通路，通过换热关联。'],
  ['heater','加热器','HEATER','热力设备','Flame','向流体侧输入热量的功率设备。'],
  ['sensor','流量计','FLOW_METER','测量与控制','Gauge','将支路流量关联到观察与曲线。'],
  ['pid','PID 控制器','PID','测量与控制','Activity','输入、设定与输出组成控制关系。'],
  ['refprop','物性测试','REFPROPTEST','自定义模块','Box','工质、组成与物性接口的编辑示例。']
];
const FLUIDS = [['water','水',125],['air','空气',3],['ammonia','氨',4],['co2','二氧化碳',17],['r134a','R134a',92],['meg30','乙二醇溶液 30%',201]];
// Project media the engine accepts (one fluid per project); keys match bridge.PROTOTYPE_MEDIA.
const MEDIA = [['water','纯液态水'],['air','空气'],['ammonia','氨'],['co2','二氧化碳'],['r134a','R134a'],['meg30','乙二醇溶液 30%']];
const SERIES = { q:{name:'主管流量',short:'主管',unit:'kg/s',color:'blue'},a:{name:'A 路流量',short:'A 路',unit:'kg/s',color:'orange'},b:{name:'B 路流量',short:'B 路',unit:'kg/s',color:'green'},pressure:{name:'出口压力',short:'压力',unit:'kPa',color:'blue'},temperature:{name:'出口温度',short:'温度',unit:'°C',color:'orange'} };
const clone = v => JSON.parse(JSON.stringify(v));
function manifestFields(manifest) {
  return manifest.parameters.filter(p => p.value_type === 'number').map(p => {
    const display = value => value / (p.unit?.display_scale || 1) + (p.unit?.display_offset || 0);
    return [p.id,p.label,p.unit?.display_unit || '',p.minimum == null ? -1e12 : display(p.minimum),p.maximum == null ? 1e12 : display(p.maximum),'any',display(p.default)];
  });
}
const defaultsFor = id => Object.fromEntries((PARAM_DEFS[id]||[]).map(f=>[f[0],f[6]]));
// Full parameter model for Python modules: numbers drive the numeric quick controls,
// while boolean/text/curve keep their own editors instead of being forced into a number input.
function manifestParamSpecs(manifest) {
  return (manifest?.parameters || []).map(p => {
    const display=value=>value==null?null:p.value_type==='number'&&p.unit?value/p.unit.display_scale+p.unit.display_offset:clone(value);
    return {id:p.id,label:p.label,value_type:p.value_type || 'number',unit:p.unit || null,
      minimum:display(p.minimum),maximum:display(p.maximum),default:display(p.default),writable:p.writable!==false,runtime:!!p.runtime};
  });
}
function manifestParamDefaults(manifest) {
  return Object.fromEntries(manifestParamSpecs(manifest).map(p => [p.id, clone(p.default)]));
}
function deviceParamSpecs(n) {
  const m = moduleOf(n);
  if (m.runtime === 'python') return manifestParamSpecs(m.manifest);
  return (PARAM_DEFS[m.kind] || []).map(f => ({id:f[0], label:f[1], value_type:'number',
    unit:f[2] ? {display_unit:f[2]} : null, minimum:f[3], maximum:f[4], default:f[6], display:f[2]}));
}
const deviceParamIds = n => deviceParamSpecs(n).map(p => p.id);
function parameterValueText(value, type) {
  if (type === 'curve') return JSON.stringify(value);
  if (value === undefined || value === null) return '';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}
function port(id,name,label,direction,domain='fluid',x=direction==='in'?20:80,y=50) { return {id,name,label,direction,domain,x,y}; }
function portsFor(id) {
  if(id==='source') return [port('out0','EX0','边界接口','out','fluid',78,50)];
  if(id==='junction') return [port('in0','IM0','公共口','in','fluid',20,50),port('out0','EX0','A 支路','out','fluid',80,30),port('out1','EX1','B 支路','out','fluid',80,70)];
  if(id==='exchanger') return [port('in0','IM0','一次侧入口','in','fluid',20,30),port('out0','EX0','一次侧出口','out','fluid',80,30),port('in1','IM1','二次侧入口','in','fluid',20,70),port('out1','EX1','二次侧出口','out','fluid',80,70)];
  if(id==='pid') return [port('in0','II0','测量输入','in','info'),port('out0','IO0','控制输出','out','info')];
  if(id==='refprop') return [port('in0','IM0','物性输入','in')];
  return [port('in0','IM0',id==='tank'?'进水口':'入口','in'),port('out0','EX0',id==='tank'?'出水口':'出口','out')];
}
// Engine state outputs of built-in state models (`<id>.state.*` in every frame), readable in curves.
const STATE_VARIABLES = {
  pipe:[['mean_temperature_k','管内平均温度（热容分段）','°C',1,-273.15],['stored_power_w','管段储热功率','W',1,0]],
  tank:[['level_m','液位','m',1,0],['mass_kg','存水质量','kg',1,0],['volume_m3','存水体积','m³',1,0],['temperature_k','水温','°C',1,-273.15],['net_inflow_kg_s','净流入流量','kg/s',1,0]]
};
function stateVariablesFor(kind) {
  return (STATE_VARIABLES[kind]||[]).map(([id,label,unit,scale,offset])=>({id:'runtime:state.'+id,name:('STATE_'+id).toUpperCase(),label,unit,type:'double',port:'',origin:'runtime',canonicalId:'state.'+id,unitSpec:{display_unit:unit,display_scale:scale,display_offset:offset},note:'引擎状态量',display:true,writable:false,value:null}));
}
function variablesFor(m) {
  const entries=[];
  for(const p of m.ports) {
    const items=p.domain==='fluid' ? [['FLOW','质量流量','kg/s',0],['PRE','绝对压力','MPa',.201325],['ENTHALPY','比焓','kJ/kg',83.9],['TEMP','温度','°C',20],['VOLUME','密度','kg/m³',998.2],['Q','干度','—',0],['X','质量组分','—',[1,0,0,0,0,0,0,0]]] : [['VALUE',p.domain==='info'?'信号值':p.domain==='power'?'电流':'转矩',DOMAINS[p.domain].unit,0]];
    for(const [suffix,label,unit,value] of items) entries.push({id:p.id+':'+suffix,name:p.name+'_'+suffix,label:p.label+' · '+label,unit,type:Array.isArray(value)?'double[8]':'double',port:p.id,origin:'port',note:suffix==='VOLUME'?'密度；参考字段 VOLUME':label,display:['FLOW','PRE'].includes(suffix),writable:p.direction==='in',value});
  }
  for(const f of PARAM_DEFS[m.kind]||[]) entries.push({id:'param:'+f[0],name:f[0].toUpperCase(),label:f[1],unit:f[2],type:'double',port:'',origin:'parameter',param:f[0],note:f[1],display:true,writable:true,value:f[6]});
  entries.push(...stateVariablesFor(m.kind));
  entries.push({id:'system:step',name:'S_T',label:'时间步长',unit:'ms',type:'int',port:'',origin:'system',note:'每次演示推进的时间',display:false,writable:true,value:100},{id:'system:run',name:'RUN_S',label:'运行状态',unit:'—',type:'int',port:'',origin:'system',note:'0：就绪 / 暂停；1：运行',display:false,writable:false,value:0},{id:'system:mix',name:'MIX',label:'工质质量比例',unit:'—',type:'double[8]',port:'',origin:'system',note:'与 FORM 顺序对应',display:false,writable:true,value:[1,0,0,0,0,0,0,0]},{id:'system:form',name:'FORM',label:'工质编号',unit:'—',type:'int[8]',port:'',origin:'system',note:'工质种类；最多 8 组分',display:false,writable:true,value:[125,0,0,0,0,0,0,0]});
  return entries;
}
function makeModule(spec) {
  const [id,name,code,category,icon,description]=spec;
  const m={id,kind:id,name,code,category,icon,description,version:1,ports:portsFor(id),channels:[],customVars:[],quickParam:(PARAM_DEFS[id]||[])[0]?.[0]||'',quickType:id==='pump'?'number':'slider',drawing:{shape:'rectangle',width:32,height:30,label:name},step:100,precision:4,dirty:false};
  if(!['source','junction','tank','refprop','pid'].includes(id)) m.channels=[{id:'ch0',name:'通路 0',input:'in0',output:'out0',kind:'resistance',enabled:true}];
  if(id==='exchanger')m.channels.push({id:'ch1',name:'通路 1',input:'in1',output:'out1',kind:'resistance',enabled:true});
  m.variables=variablesFor(m);m.values=Object.fromEntries(m.variables.map(v=>[v.id,clone(v.value)]));
  m.banks=[clone(m.values),clone(m.values),clone(m.values)];m.bankNames=['额定工况','部分负荷','调试备份'];
  if(id==='valve'){m.banks[1]['param:opening']=65;m.banks[2]['param:opening']=40;}
  m.source = pythonModuleSource(id, code); m.sourceFormat = 'python-v1';
  return m;
}
function makeInstance(id,kind,name,x,y,params={}) { const p={...defaultsFor(kind),...params};return {id,moduleId:kind,name,x,y,rotation:0,params:p,draft:clone(p),modelId:kind==='valve'?'valve-16':kind==='pump'?'pump-standard':null,modelVersion:1,draftModelId:null}; }
function waterPage(){return {id:'main',name:'主系统',zoom:1,pan:[0,0],nodes:[makeInstance('B1','source','供水边界',70,225),makeInstance('P1','pump','循环泵',230,225),makeInstance('N1','junction','分流节点',380,225),makeInstance('V1','valve','A 路调节阀',515,135),makeInstance('L1','pipe','A 路管道',685,135),makeInstance('V2','valve','B 路调节阀',515,335,{opening:55}),makeInstance('L2','pipe','B 路管道',685,335,{length:40}),makeInstance('N2','junction','汇流节点',830,225),makeInstance('B2','source','回水边界',975,225,{pressure:120})],edges:[['e1','B1','out0','P1','in0'],['e2','P1','out0','N1','in0'],['e3','N1','out0','V1','in0'],['e4','V1','out0','L1','in0'],['e5','L1','out0','N2','out0'],['e6','N1','out1','V2','in0'],['e7','V2','out0','L2','in0'],['e8','L2','out0','N2','out1'],['e9','N2','in0','B2','out0']]};}
function heatPage(){return {id:'main',name:'一次与二次回路',zoom:1,pan:[0,0],nodes:[makeInstance('B1','source','一次侧供水',100,155,{temperature:65}),makeInstance('P1','pump','一次泵',290,155),makeInstance('HX1','exchanger','板式换热器',545,235),makeInstance('B2','source','一次侧回水',825,155,{pressure:120}),makeInstance('B3','source','二次侧供水',100,335,{temperature:25}),makeInstance('P2','pump','二次泵',290,335),makeInstance('B4','source','二次侧回水',825,335,{pressure:120})],edges:[['h1','B1','out0','P1','in0'],['h2','P1','out0','HX1','in0'],['h3','HX1','out0','B2','out0'],['h4','B3','out0','P2','in0'],['h5','P2','out0','HX1','in1'],['h6','HX1','out1','B4','out0']]};}
function tankPage(){return {id:'main',name:'储水与调节',zoom:1,pan:[0,0],nodes:[makeInstance('B1','source','补水边界',120,230),makeInstance('V1','valve','进水调节阀',330,230,{opening:65}),makeInstance('TK1','tank','储水罐',540,230),makeInstance('V2','valve','出水调节阀',750,230,{opening:40}),makeInstance('B2','source','回水边界',960,230,{pressure:120})],edges:[['t1','B1','out0','V1','in0'],['t2','V1','out0','TK1','in0'],['t3','TK1','out0','V2','in0'],['t4','V2','out0','B2','out0']]};}
function emptyRun(scope='project') {return {scope,status:'ready',time:0,step:.1,history:[],events:[],id:'',values:{q:0,a:0,b:0,pressure:0,temperature:20}};}
function controlTemplate() {return `def initialize(ctx):
    ctx.state["samples"] = 0


def step(ctx, dt_s):
    flow = ctx.read("V1.mass_flow_kg_s")
    ctx.write("V1.param.opening_ratio", 0.65)
    ctx.state["samples"] += 1
    ctx.log(f"flow={flow:.3f} kg/s")


def finalize(ctx):
    pass
`;}
function makeProject(id,name,description,page){return {id,name,description,pages:[page],activePage:'main',modified:'示例项目',medium:'water',run:emptyRun(),solver:{duration:30,dt:.1,massAtol:1e-7,pressureAtol:.1,maxIter:80,mode:'dynamic',hydraulicMethod:'auto',moduleMixedJacobian:true},control:controlTemplate(),controlLanguage:'python',controlEnabled:false,controlInputs:'V1.mass_flow_kg_s',controlOutputs:'V1.param.opening_ratio',dirty:false};}

function initialState(){
  const modules=MODULE_SPECS.map(makeModule);
  const makeModel=(id,moduleId,name,params,description)=>({id,moduleId,name,description,version:1,params:{...defaultsFor(moduleId),...params},bank:1,archived:false,versions:[{version:1,note:'首次保存型号',params:{...defaultsFor(moduleId),...params}}]});
  return {schema:1,moduleGroups:[],projects:[makeProject('water-net','泵阀并联管网','观察阀门调节后两条支路的流量分配。',waterPage()),makeProject('heat-loop','双侧换热机组','两个独立水回路与换热设备的联动示例。',heatPage()),makeProject('tank-control','水箱液位调节','开式水箱在进出水阀调节下的液位与水温变化。',tankPage())],activeProject:'water-net',modules,
    models:[makeModel('valve-16','valve','调节阀 · Kv16',{},'标准调节阀，默认开度 80%。'),makeModel('valve-25','valve','调节阀 · Kv25',{kv:25,opening:65},'大流量型号，部分负荷工况。'),makeModel('pump-standard','pump','标准离心泵',{},'额定转速，泵效率 75%。'),makeModel('heat-standard','exchanger','板换 · UA2000',{},'一次侧与二次侧独立配置。'),makeModel('tank-5','tank','储水罐 · 5m³',{},'用于水箱液位调节场景。')],
    selectedModule:'valve',selectedModel:'valve-16',bench:{moduleId:'valve',params:defaultsFor('valve'),boundary:{inlet:201.325,outlet:120,temperature:20},run:emptyRun('bench')},
    records:[],
    charts:{series:{q:true,a:true,b:true},extra:[],compare:false,source:'live',range:'window'},
    connectors:[{id:'serial1',name:'实验台串口',kind:'serial',port:'COM3',baud:'115200',connected:false},{id:'api1',name:'本地变量接口',kind:'http',port:'8765',connected:false}],
    messages:[{time:'示例',kind:'INFO',text:'已载入泵阀并联管网示例。'},{time:'示例',kind:'CHECK',text:'项目、模块、型号、控制与曲线可切换查看。'}],
    savedAt:null,dirty:false,serial:21
  };
}

const root=document.getElementById('fn-studio');
const page=document.getElementById('page');
const controls=window.FluidNetControls;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=name=>ICONS[name]||ICONS.Box;
const number=(n,d=2)=>n !== null && n !== undefined && Number.isFinite(Number(n))?Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const btn=(action,label,glyph='',attrs='',style='')=>`<button type="button" class="btn ${style}" data-action="${action}" ${attrs}>${glyph?icon(glyph):''}${label}</button>`;
const ibtn=(action,label,glyph,attrs='')=>`<button type="button" class="icon-btn" data-action="${action}" aria-label="${esc(label)}" title="${esc(label)}" ${attrs}>${icon(glyph)}</button>`;
const badge=(label,type='')=>`<span class="badge ${type}">${label}</span>`;
const empty=(title,description,action='')=>`<div class="empty">${icon('FolderOpen')}<h3>${title}</h3><p>${description}</p>${action}</div>`;
const option=(value,label,current)=>`<option value="${esc(value)}"${String(value)===String(current)?' selected':''}>${esc(label)}</option>`;
const clockLabel=t=>`t = ${number(t,1)} s`;
let recovery='', editRevision=0, savePhase='', saveError='', localSaveError='', localSaveTrimmed=false;
let state=initialState();
try { const saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');if(saved&&saved.schema===1&&Array.isArray(saved.projects)&&saved.projects.length&&Array.isArray(saved.modules)&&saved.modules.length&&Array.isArray(saved.models)){state=saved;state.projects.forEach(p=>{if(p.run.status==='running')p.run.status='paused';});if(state.bench.run.status==='running')state.bench.run.status='paused';} } catch { recovery='上次原型记录无法读取，已打开内置示例。'; }
const ui={route:'home',theme:matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light',moduleTab:'drawing',selectedNode:'',selectedEdge:'',editorPort:'',category:'全部模块',moduleSearch:'',moduleView:'cards',projectSearch:'',projectFilter:'all',projectView:'grid',bank:0,allBanks:false,variableSearch:'',onlyCommon:false,valueSearch:'',arrayVar:'system:form',codeKind:'runtime',designIndex:0,modelSearch:'',modelFilter:'all',modelTab:'parameters',benchTab:'results',settingsTab:'project',connectionTab:'variables',selectedConnector:'serial1',nodeDomain:'fluid',nodeTab:'definition',selectedRecord:'DEMO-003',runFilter:'all',pageGrid:false,placing:null,connecting:null,canvasMode:'select',floats:[],frontId:'',floatSerial:0,taskDrawer:false,selectedChart:'q',clipboard:null,showLibrary:innerWidth>500,showChart:false,workbenchChart:'flow',compileOutput:'尚未检查。可检查 Python 括号与字符串，或预览模块调用流程。',controlOutput:'控制脚本尚未预览。',connectionSearch:'',guideStep:0};
try {const savedUI=JSON.parse(localStorage.getItem(UI_KEY)||'null');if(savedUI){for(const key of ['theme','moduleTab','settingsTab','connectionTab','bank','pageGrid','codeKind','designIndex','showLibrary','showChart','workbenchChart','moduleView'])if(savedUI[key]!==undefined)ui[key]=savedUI[key];}}catch{}
if (!['cards','list'].includes(ui.moduleView)) ui.moduleView = 'cards';
if (['design','header'].includes(ui.moduleTab)) { ui.codeKind=ui.moduleTab; ui.moduleTab='code'; }
if (!['runtime','design','header'].includes(ui.codeKind)) ui.codeKind='runtime';
if (![0,1,2].includes(ui.designIndex)) ui.designIndex=0;
let modal=null,contextMenu=null,pointer=null,toastTimer,runInterval,undoStack=[],redoStack=[],lastTick=0;
const project=()=>state.projects.find(p=>p.id===state.activeProject)||state.projects[0];
const activePage=()=>project().pages.find(p=>p.id===project().activePage)||project().pages[0];
const mod=(id=state.selectedModule)=>state.modules.find(m=>m.id===id)||state.modules[0];
const instance=id=>project().pages.flatMap(p=>p.nodes).find(n=>n.id===id);
const moduleOf=n=>ownerOfInstance(n)?.moduleSnapshots?.[n.moduleId] || mod(n.moduleId);
const model=(id=state.selectedModel)=>state.models.find(m=>m.id===id);
const paramDefs=n=>moduleOf(n).runtime === 'python' ? manifestFields(moduleOf(n).manifest) : PARAM_DEFS[moduleOf(n).kind]||[];
const pendingCount=n=>deviceParamIds(n).filter(id=>!sameValue(n.draft[id],n.params[id])).length+instanceCustomPending(n)+(n.draftModelId&&(n.draftModelId!==n.modelId||n.draftModelVersion!==n.modelVersion)?1:0);
const anyPending=()=>state.projects.reduce((sum,p)=>sum+p.pages.flatMap(p=>p.nodes).reduce((s,n)=>s+pendingCount(n),0),0);
const statusText=run=>({ready:'就绪',running:'运行中',paused:'已暂停',stopped:'已停止',completed:'已完成',failed:'失败',solving:'求解中'}[run.status]||'就绪');
function msg(text,error=false){const toast=document.getElementById('toast');toast.className='toast'+(error?' error':'');toast.innerHTML=icon(error?'Info':'CheckCircle2')+`<span>${esc(text)}</span>`;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.hidden=true,3500);document.getElementById('announcement').textContent=text;}
function saveUI(){try{localStorage.setItem(UI_KEY,JSON.stringify({theme:ui.theme,moduleTab:ui.moduleTab,settingsTab:ui.settingsTab,connectionTab:ui.connectionTab,bank:ui.bank,pageGrid:ui.pageGrid,codeKind:ui.codeKind,designIndex:ui.designIndex,showLibrary:ui.showLibrary,showChart:ui.showChart,workbenchChart:ui.workbenchChart,moduleView:ui.moduleView}));}catch{/* 界面偏好体积很小；失败只影响主题/页签记忆，草稿失败由 persistLocal 提示。 */}}
// 配额类存储异常：Chrome/Edge 的 QuotaExceededError、Firefox 的 NS_ERROR_DOM_QUOTA_REACHED，
// 旧浏览器报 code 22（QUOTA_EXCEEDED_ERR）或 1014，另外按 name/message 兜底。
function isQuotaError(error){
  if(!error)return false;
  const name=String(error.name||''), message=String(error.message||'');
  return /quota/i.test(name)||name==='NS_ERROR_DOM_QUOTA_REACHED'||error.code===22||error.code===1014
    ||/quota|exceeded the quota|storage space|存储空间/i.test(message);
}
// 在“仅用于存储”的副本上裁剪运行历史：每次运行保留最近 frames 帧，运行快照保留最近 records 条
// （null 表示不裁剪快照）。只改副本；返回是否真的裁掉了内容。
function trimDraft(draft,frames,records){
  let trimmed=false;
  const trim=run=>{if(!run||!Array.isArray(run.history)||run.history.length<=frames)return;run.history=run.history.slice(-frames);trimmed=true;};
  for(const p of draft.projects||[])trim(p.run);
  trim(draft.bench?.run);
  if(Array.isArray(draft.records)){
    if(records!==null&&draft.records.length>records){draft.records=draft.records.slice(0,records);trimmed=true;}
    for(const record of draft.records)trim(record);
  }
  return trimmed;
}
function failLocalSave(text){
  const repeat=localSaveError===text;
  localSaveError=text;localSaveTrimmed=false;syncChrome();
  if(!repeat)msg(text,true);
  return false;
}
// 依次产出可写入的草稿文本：第一项为原样 state，之后为逐级裁剪运行历史的副本（懒生成，
// 前一项写入成功就不再序列化后面的副本）。内存中的 state 不会被修改。
function* draftTexts(){
  let last='', draft=null;
  for(const step of [null,...LOCAL_DRAFT_STEPS]){
    let text;
    if(step===null)text=JSON.stringify(state);
    else{
      draft||=clone(state);
      if(!trimDraft(draft,step[0],step[1]))continue;
      text=JSON.stringify(draft);
    }
    if(text===last)continue;
    last=text;
    yield {frames:step?step[0]:null,text};
  }
}
// 统一的本地草稿写入（“保存原型”与引擎/流程里的 ui.persist 共用）：
// 先原样写；配额不足时按 LOCAL_DRAFT_STEPS 逐级裁剪副本重试；全部失败则保留内存数据并显示可见错误。
function persistLocal(){
  try{
    for(const {frames,text} of draftTexts()){
      try{localStorage.setItem(STORAGE_KEY,text);}
      catch(error){if(isQuotaError(error))continue;return failLocalSave('本地草稿保存失败：'+(error.message||'浏览器拒绝写入')+'；内存数据仍在，请导出原型。');}
      if(frames===null){if(localSaveError||localSaveTrimmed){localSaveError='';localSaveTrimmed=false;syncChrome();}return true;}
      const first=!localSaveTrimmed;
      localSaveError='';localSaveTrimmed=true;syncChrome();
      if(first)msg(`浏览器草稿已保存；存储空间不足，运行历史已裁剪为最近 ${frames} 帧，完整曲线仍在内存，请导出原型。`);
      return true;
    }
    return failLocalSave('本地草稿保存失败：存储空间不足，已保留内存数据，请导出原型后清理浏览器存储。');
  }catch(error){return failLocalSave('本地草稿保存失败：'+(error.message||'未知错误')+'；内存数据仍在，请导出原型。');}
}
// 载入服务器工作区、导入或恢复示例前备份当前草稿；配额不足时同样裁剪副本，
// 仍放不下就抛出可见原因，避免静默丢掉旧草稿。
function backupLocalDraft(key){
  try{
    for(const {text} of draftTexts()){
      try{localStorage.setItem(key,text);return true;}
      catch(error){if(isQuotaError(error))continue;throw Error('本地草稿备份失败：'+(error.message||'浏览器拒绝写入'));}
    }
  }catch(error){if(!/^本地草稿备份失败/.test(error.message||''))throw Error('本地草稿备份失败：'+(error.message||'未知错误')+'，请先导出原型再继续。');throw error;}
  throw Error('本地草稿备份失败：存储空间不足，请先导出原型再继续。');
}
function markDirty(target){editRevision++;if(savePhase==='saved')savePhase='';state.dirty=true;if(target)target.dirty=true;root.querySelectorAll("[data-float-save]").forEach(el=>el.textContent="草稿未保存");syncChrome();}
async function saveAll(){
  if(savePhase==='saving')return;
  const owner=state, version=editRevision, payload=clone(state);
  payload.dirty=false;payload.savedAt=new Date().toISOString();payload.projects.forEach(p=>p.dirty=false);
  payload.modules.forEach(m=>{if(m.runtime!=='python')m.dirty=false;});
  savePhase='saving';saveError='';syncChrome();
  // 本地草稿先落盘：失败不再静默——persistLocal 会按策略裁剪副本重试，仍失败则显示可见错误，
  // 内存中的 state 保持完整，用户仍可导出原型。
  persistLocal();
  try{
    const receipt=await engine.saveWorkspace(payload);
    if(state===owner){
      state.workspaceRevision=receipt.revision;state.savedAt=receipt.saved_at;
      if(editRevision===version){state.dirty=false;state.projects.forEach(p=>p.dirty=false);state.modules.forEach(m=>{if(m.runtime!=='python')m.dirty=false;});}
      persistLocal();
    }
    savePhase='saved';syncChrome();updateFloatBodies();
    msg(`工作区已保存 · 修订 ${receipt.revision}${state.dirty?' · 仍有后续修改未保存':''}${anyPending()?` · ${anyPending()} 项参数待应用`:''}`);
  }catch(error){savePhase='error';saveError=error.message;state.dirty=true;persistLocal();syncChrome();msg('保存失败：'+error.message,true);}
}
function restoreWorkspace(data){
  const incoming=clone(data);
  validateImport(incoming);
  backupLocalDraft(STORAGE_KEY+'-before-workspace');
  const previous=state;
  try{state=incoming;normalizeState();}catch(error){state=previous;throw error;}
  ui.floats=[];ui.selectedNode='';undoStack=[];redoStack=[];
  editRevision++;savePhase='';saveError='';render();
}
async function workspaceTools(){
  const [usage,history]=await engine.workspaceInfo();
  openDialog('工作区备份与恢复','备份包含已保存的项目、运行历史和模块版本；当前未保存草稿请先保存或导出。',`
    <div class="stack"><div class="row">${btn('download-backup','下载完整备份','Download','','primary')}${btn('choose-backup','恢复备份到新目录','FolderOpen')}${btn('export-old-draft','导出载入前草稿','FileJson')}</div>
    <input id="workspace-backup-file" type="file" accept=".zip,application/zip" data-workspace-backup hidden>
    <div class="notice">恢复前校验全部文件、数据库与模块哈希；恢复到独立目录后，按提示重启服务。当前工作区保留。</div>
    <p>数据库 ${number(usage.database_bytes/1024**2,2)} MiB · 可复用 ${number(usage.reusable_bytes/1024**2,2)} MiB · WAL ${number(usage.wal_bytes/1024**2,2)} MiB · 磁盘可用 ${number(usage.free_disk_bytes/1024**3,1)} GiB</p>
    <p>运行 ${usage.runs} 条 · 窗口帧 ${usage.frames} 条 · 保留 ${usage.run_retention} 次终态运行与 ${usage.revision_retention} 个工作区修订</p>
    <h3>恢复已保存的工作区修订</h3>${history.revisions.map(r=>`<div class="row spread"><span>修订 ${r.revision} · ${esc(r.saved_at)}</span>${btn('restore-workspace-revision','恢复此修订','History',`data-revision="${r.revision}"`)}</div>`).join('')||'<p>暂无已保存修订。</p>'}</div>`,null,'',true);
}
root.addEventListener('change',async event=>{
  if(!('workspaceBackup' in event.target.dataset))return;
  const file=event.target.files[0];if(!file)return;
  try{msg('正在校验并恢复备份…');const result=await engine.restoreBackup(file);
    openDialog('备份已恢复',result.message,`<div class="stack"><p>修订 ${result.revision}</p><p class="mono">${esc(result.directory)}</p><pre class="code-preview">${esc(result.command)}</pre></div>`,null,'',true);
  }catch(error){msg(error.message,true);}
});
function receiveArchives(runs){
  ui.archivedRuns=runs;
  for(const p of state.projects)if(p.run.live && !runs.some(r=>r.id===p.run.runId)){
    p.run.live=false;p.run.runId=null;p.run.status='stopped';p.run.events.push({t:p.run.time,text:'原运行已过期，请新建运行。'});
  }
  if(ui.route==='runs')render();
}
function showArchive(record,overview){
  const source=record.request.project;
  const history=overview.rows.map(frame=>({t:frame.time_s,canonical:frame.variables,variables:{},variableValues:{},diagnostics:frame.diagnostics,metrics:frame.metrics,
    q:frame.variables['P1.mass_flow_kg_s']??null,a:frame.variables['V1.mass_flow_kg_s']??null,b:frame.variables['V2.mass_flow_kg_s']??null,
    pressure:Number.isFinite(frame.variables['P1.out0.pressure_pa'])?frame.variables['P1.out0.pressure_pa']/1000:null,
    temperature:Number.isFinite(frame.variables['P1.out0.temperature_k'])?frame.variables['P1.out0.temperature_k']-273.15:null}));
  const item={id:record.id,name:source.name,projectName:source.name,projectId:state.projects.find(p=>p.id===source.id)?.id,
    scope:'project',status:record.status,mode:record.mode==='steady'?'稳态':'动态',time:record.frame?.time_s||0,
    history,events:record.events.map(e=>({t:e.time_s,text:e.message||e.type})),
    params:Object.fromEntries(source.instances.map(n=>[n.id,n.parameters])),source:'engine',sample:false,
    archive:record,archiveStride:overview.stride,totalRows:overview.total_rows,
    chartBindings:source.thermal_couplings?.length?clone(state.charts.extra.filter(v=>v.projectId===source.id&&!isCouplingChart(v)))
      .concat(coldStorage.couplingChartBindings({id:source.id,thermalCouplings:source.thermal_couplings})):undefined};
  state.records=state.records.filter(r=>r.id!==item.id);state.records.unshift(item);state.records=state.records.slice(0,30);
  ui.selectedRecord=item.id;render();
}
function log(text,kind='INFO'){state.messages.unshift({time:new Date().toLocaleTimeString('zh-CN',{hour12:false}),kind,text});state.messages=state.messages.slice(0,80);}
function isCouplingChart(binding) {
  return Boolean(binding.couplingId||binding.couplingTotal||binding.canonicalKey?.startsWith('coupling.')||binding.canonicalKey?.startsWith('metrics.coupling_'));
}
function canvasEditSnapshot(owner=project()) {
  return clone({pages:owner.pages,activePage:owner.activePage,thermalCouplings:owner.thermalCouplings,
    charts:state.charts.extra.filter(binding=>binding.projectId===owner.id),workbenchChart:ui.workbenchChart,showChart:ui.showChart});
}
function remember(){undoStack.push(canvasEditSnapshot());if(undoStack.length>30)undoStack.shift();redoStack=[];}
function undo(redo=false) {
  const from=redo?redoStack:undoStack,to=redo?undoStack:redoStack;if(!from.length)return;
  const owner=project(),next=from.at(-1);
  // Restoring a canvas can also remove or restore a coupling endpoint. A live run
  // owns its original topology, including when paused.
  if(owner.thermalCouplings?.length||next.thermalCouplings?.length)coldStorage.assertCouplingIdle(owner);
  to.push(canvasEditSnapshot(owner));from.pop();owner.pages=next.pages;owner.activePage=next.activePage;
  if('thermalCouplings' in next)owner.thermalCouplings=next.thermalCouplings;else delete owner.thermalCouplings;
  state.charts.extra=state.charts.extra.filter(binding=>binding.projectId!==owner.id).concat(next.charts);
  ui.workbenchChart=next.workbenchChart;ui.showChart=next.showChart;
  ui.selectedNode='';ui.selectedEdge='';ui.connecting=null;ui.pinnedChart=null;
  ui.floats=ui.floats.filter(f=>instance(f.id));markDirty(owner);persistLocal();render();msg(redo?'已重做':'已撤销');
}
function navigate(route,options={}){if(!PAGE_META[route])route='home';if(ui.route!==route)ui.pinnedChart=null;Object.assign(ui,options);ui.route=route;contextMenu=null;ui.taskDrawer=false;if(location.hash!==`#${route}`)history.replaceState(null,'',`#${route}`);saveUI();render();page.scrollTop=0;if(route==='runs')engine.refreshArchives();}
function openProject(id){if(!state.projects.some(p=>p.id===id))return;state.activeProject=id;ui.pinnedChart=null;ui.chartCursor=null;ui.selectedNode='';ui.floats=[];undoStack=[];redoStack=[];navigate('workbench');}
function openEditor(id,tab='drawing',origin=null){ui.editorOrigin=origin;state.selectedModule=id;ui.editorPort='';ui.moduleTab=['design','header'].includes(tab)?'code':tab;if(['design','header'].includes(tab))ui.codeKind=tab;ui.arrayVar='system:form';navigate('editor');}
function heading(title,subtitle,actions='',eyebrow=''){return `<div class="page-heading"><div>${eyebrow?`<div class="eyebrow">${eyebrow}</div>`:''}<h1>${title}</h1><p>${subtitle}</p></div><div class="row wrap">${actions}</div></div>`;}
function renderHeader(){document.getElementById('app-header').innerHTML=`<button class="brand" data-action="nav" data-route="home" aria-label="FluidNet Studio 首页"><span class="brand-mark">${icon('Network')}</span>FluidNet <span class="brand-sub">Studio</span></button><span class="header-rule"></span><button class="project-picker" data-action="project-picker">${icon('FolderOpen')}<span>${esc(project().name)}</span>${icon('ChevronDown')}</button>${badge(engine?.health ? '模块平台 · v' + engine.health.version : '连接计算服务…',engine?.health ? 'good' : 'warn')}<button class="header-search" data-action="page-map" aria-label="页面导航与快捷入口">${icon('Search')}<span>页面与操作</span><kbd>Ctrl K</kbd></button><span class="save-indicator" data-save-status></span>${btn('workspace-tools','备份与恢复','Database')+btn('reload-workspace','载入服务器','FolderOpen','title="载入服务器工作区，当前草稿会先备份到浏览器"')+btn('save','<span>保存原型</span>','Save','title="保存全部项目、模块、型号和界面状态；待应用参数仍需单独应用"','header-save')}${ibtn('theme',ui.theme==='dark'?'切换浅色':'切换深色',ui.theme==='dark'?'Sun':'Moon')}${ibtn('nav','使用指南','CircleHelp','data-route="help"')}`;}
function renderRail(){const ids=['home','projects','workbench','modules','bench','models','curves','runs','batches','controls','connections'];document.getElementById('app-rail').innerHTML=ids.map(id=>`${id==='modules'||id==='controls'?'<div class="rail-divider"></div>':''}<button type="button" class="rail-link${ui.route===id||ui.route==='editor'&&id==='modules'||ui.route==='nodes'&&id==='modules'?' active':''}" data-action="nav" data-route="${id}" title="${PAGE_META[id][2]}"${ui.route===id?' aria-current="page"':''}>${icon(PAGE_META[id][1])}<span>${PAGE_META[id][0]}</span></button>`).join('')+`<div class="rail-bottom"><div class="rail-divider"></div><button class="rail-link${ui.route==='settings'?' active':''}" data-action="nav" data-route="settings">${icon('Settings2')}<span>设置</span></button></div>`;}
function syncChrome(){
  const save=root.querySelector('[data-save-status]');if(save){save.title=localSaveError||saveError||'';save.classList.toggle('dirty',state.dirty||!!localSaveError);save.innerHTML=`<span class="dot"></span>${localSaveError?'本地草稿保存失败 · 请导出原型':savePhase==='saving'?'正在保存…':savePhase==='error'?'保存失败 · 可重试':state.dirty?'有未保存修改':localSaveTrimmed?'草稿已裁剪保存':state.savedAt?'工作区已保存':'示例已就绪'}`;}
  const run=project().run;const active=state.projects.filter(p=>p.run.status==='running'||p.run.status==='paused');
  document.getElementById('statusbar').innerHTML=`<span class="row gap-6"><span class="dot" style="color:var(--${run.status==='running'?'green':'muted'})"></span>${esc(project().name)} · ${statusText(run)}</span><span class="mono" data-live-time>${clockLabel(run.time)}</span>${active.length?`<button class="task-chip" data-action="tasks">${icon('Activity')} ${active.length} 个运行任务</button>`:''}<span class="optional">${currentProjectPending()?`当前项目 ${currentProjectPending()} 项待应用`:'当前项目参数已生效'}</span><span class="push"></span><button data-action="page-map" class="optional">页面导览</button><span class="prototype-label">单相流体网络 · Python 控制</span>`;syncWorkbenchStatus();
}
function render(){root.dataset.theme=ui.theme;renderHeader();renderRail();const views={home:renderHome,projects:renderProjects,workbench:renderWorkbench,modules:renderModules,bench:renderBench,editor:renderEditor,nodes:renderNodesPage,models:renderModels,curves:renderCurves,runs:renderRuns,batches:()=>scenarioBatches.markup(project()),controls:renderControls,connections:renderConnections,settings:renderSettings,help:renderHelp};page.innerHTML=(views[ui.route]||renderHome)();renderFloats();syncChrome();renderDialog(false);requestAnimationFrame(()=>{resizeCharts();restoreChartCursor();if(ui.route==='connections'&&ui.connectionTab==='api')apiPreview();});if(recovery){msg(recovery,true);recovery='';}scenarioBatches.afterRender();}
function thumbnail(p){return `<svg viewBox="0 0 1100 470" role="img" aria-label="${esc(p.name)}管网预览">${networkMarkup(p.pages[0],true)}</svg>`;}
function projectCard(p){return `<article class="project-card"><button class="project-preview" data-action="open-project" data-id="${p.id}" aria-label="打开 ${esc(p.name)}">${thumbnail(p)}${badge(p.id===state.activeProject?'当前项目':'示例','')}</button><div class="project-info"><h3>${esc(p.name)}</h3><div class="meta"><span>${p.pages.length} 张画布</span><span>·</span><span>${p.pages.reduce((s,c)=>s+c.nodes.length,0)} 个设备</span><span>·</span><span>${p.caseId==='cold-room-ideal-v1'?'库房热系统':esc(fluidBadge(p))}</span></div><div class="row spread"><small class="muted">${p.dirty?'草稿有修改':esc(p.modified||'示例项目')}</small><div class="row gap-6">${workflows.projectActions(p)}${ibtn('duplicate-project','复制项目','Copy',`data-id="${p.id}"`)}${btn('open-project','打开','ArrowUpRight',`data-id="${p.id}"`,'small')}</div></div></div></article>`;}
function renderHome(){return `<div class="page-shell">${heading('工作从这里开始','继续建模，或从一个验证过操作流程的示例开始。',btn('import','导入原型','Upload')+btn('new-project','新建项目','Plus','','primary'),'FLUIDNET WORKSPACE')}${entryPathsMarkup()}<div class="home-main"><div class="stack gap-20"><section><div class="section-title"><h2>最近项目</h2>${btn('nav','全部项目','ChevronRight','data-route="projects"','ghost small')}</div><div class="project-grid">${state.projects.slice(0,3).map(projectCard).join('')}</div></section><section class="panel"><div class="panel-head"><h2>最近使用的模块</h2>${btn('nav','模块库','ArrowUpRight','data-route="modules"','ghost small')}</div>${['valve','pump','exchanger','tank'].map(id=>{const m=mod(id);return `<div class="list-row"><span class="object-icon">${icon(m.icon)}</span><div class="grow"><strong>${m.name}</strong><small>${m.code} · ${m.ports.length} 个端口 · ${m.channels.length} 条内部通路</small></div>${badge('v'+m.version)}${btn('edit-module','编辑定义','Pencil',`data-id="${id}"`,'ghost small')}</div>`;}).join('')}</section></div><aside class="home-aside stack"><section class="panel"><div class="panel-head"><h2>快捷入口</h2>${icon('Grid2X2')}</div><div class="quick-list">${[['new-module','新建算法模块','Box'],['nav','管理设备型号','Database','models'],['nav','查看运行记录','History','runs'],['nav','页面与使用指南','BookOpen','help']].map(([act,label,i,r])=>`<button data-action="${act}" ${r?`data-route="${r}"`:''}>${icon(i)}<span class="grow">${label}</span>${icon('ChevronRight')}</button>`).join('')}</div></section><section class="panel"><div class="panel-head"><h2>消息与任务</h2>${badge('本地原型')}</div><div class="timeline">${state.messages.slice(0,3).map(m=>`<div class="timeline-item"><span class="timeline-point">${icon('CheckCircle2')}</span><div>${esc(m.text)}<small>${m.time} · ${m.kind}</small></div></div>`).join('')}</div></section><section class="panel"><div class="panel-body stack"><div class="row">${icon('Info')}<strong>当前体验范围</strong></div><p class="muted" style="font-size:12px">主系统运行已接入真实水力与热力求解。含水箱或管道热容分段的项目按隐式 Euler 积分液位、水温与管内温度，其余动态为准稳态时间序列。动态运行是可暂停、单步和运行中改参数的会话；「控制」页可配置 PID（Lua 控制脚本尚未接入）。Python 模块支持独立验证与版本保存。</p>${btn('page-map','查看全部页面','LayoutDashboard','','small')}</div></section></aside></div></div>`;}
function renderProjects(){let list=state.projects.filter(p=>(p.name+p.description).toLowerCase().includes(ui.projectSearch.toLowerCase()));if(ui.projectFilter==='current')list=list.filter(p=>p.id===state.activeProject);return `<div class="page-shell">${heading('项目管理','按项目保存、导入导出与恢复修订；运行记录独立保存。',workflows.projectToolbar()+btn('cs-create','−18°C 冷库案例','Thermometer')+btn('cs-create-station','NH₃/CO₂ 冷库案例','Wind')+btn('cs-create-coupled','制冷站热耦合','ArrowRightLeft')+btn('cs-create-dual','双盘管示例','Network')+btn('import','导入原型','Upload')+btn('new-project','新建项目','Plus','','primary'))}<div class="filterbar"><label class="search">${icon('Search')}<input aria-label="搜索项目" data-filter="projectSearch" placeholder="搜索项目名称" value="${esc(ui.projectSearch)}"></label><div class="segmented">${[['all','全部项目'],['current','当前项目']].map(([k,v])=>`<button data-action="project-filter" data-value="${k}" class="${ui.projectFilter===k?'active':''}">${v}</button>`).join('')}</div><span class="push"></span><span class="muted">${list.length} 个项目</span><div class="segmented">${['grid','list'].map(k=>`<button aria-label="${k==='grid'?'卡片视图':'列表视图'}" data-action="project-view" data-value="${k}" class="${ui.projectView===k?'active':''}">${icon(k==='grid'?'Grid2X2':'List')}</button>`).join('')}</div></div><div id="project-results" class="project-grid${ui.projectView==='list'?' project-list-view':''}">${list.map(projectCard).join('')||empty('没有匹配的项目','换个关键词，或新建一个项目。')}</div><div class="home-note"><span class="note-icon">${icon('Folder')}</span><div class="grow"><strong>项目与修订保存在服务器工作区</strong><p>“管理”可单独保存项目、导出及恢复修订；“保存原型”保存完整工作区。</p></div>${btn('export','导出原型','Download','data-format="prototype"','ghost')}</div></div>`;}
function symbol(n,mini=false){const kind=moduleOf(n).kind;let s='';const stroke='var(--muted)',fill='var(--surface)';if(kind==='junction')s=`<circle r="5" fill="var(--orange)"/>`;else if(kind==='source')s=`<circle r="17" fill="var(--blue-soft)" stroke="var(--blue)" stroke-width="1.3"/><text y="4" text-anchor="middle" font-size="13" fill="var(--blue)">P</text>`;else if(kind==='pump')s=`<circle r="18" fill="var(--soft)" stroke="${stroke}" stroke-width="1.3"/><path d="M -5 -9 L 10 0 L -5 9 Z" fill="none" stroke="${stroke}" stroke-width="1.5"/><path d="M -13 22 H 13" stroke="${stroke}" stroke-width="2"/>`;else if(kind==='valve'||kind==='check')s=`<path d="M -15 -10 L 15 10 V -10 L -15 10 Z" fill="${fill}" stroke="var(--accent)" stroke-width="1.4"/>${kind==='check'?'<path d="M 0 -13 V 13" stroke="var(--accent)"/>':''}`;else if(kind==='pipe')s=`<rect x="-22" y="-5" width="44" height="10" rx="2" fill="${fill}" stroke="var(--accent)" stroke-width="1.3"/>`;else if(kind==='tank')s=`<rect x="-20" y="-28" width="40" height="56" rx="7" fill="var(--blue-soft)" stroke="${stroke}" stroke-width="1.3"/><path d="M -18 0 Q -9 -5 0 0 T 18 0" fill="none" stroke="var(--blue)"/>`;else if(kind==='exchanger')s=`<rect x="-29" y="-32" width="58" height="64" rx="5" fill="${fill}" stroke="${stroke}"/><path d="M -25 -17 H 23 M -25 17 H 23 M -10 -23 L 10 23 M 0 -23 L 20 23" stroke="var(--orange)" fill="none"/>`;else s=`<rect x="-18" y="-18" width="36" height="36" rx="6" fill="var(--soft)" stroke="${stroke}"/><text y="4" text-anchor="middle" fill="var(--text)" font-size="11">${kind==='heater'?'Q':kind==='pid'?'PID':kind==='sensor'?'F':'ƒ'}</text>`;return `<g transform="rotate(${n.rotation||0})">${s}</g>`;}
function portOffset(n,p){if(moduleOf(n).kind==='source')return {x:/^B[24](?:-|$)/.test(n.id)?-28:28,y:0};if(moduleOf(n).kind==='junction'){const flip=/^N2(?:-|$)/.test(n.id)?-1:1;return p.id==='in0'?{x:-24*flip,y:0}:{x:24*flip,y:p.id==='out0'?-18:18};}const m=moduleOf(n);if(m.category==='制冷站设备'){const side=m.ports.filter(q=>q.direction===p.direction),i=side.indexOf(p);return {x:p.direction==='in'?-32:32,y:side.length>1?-21+42*i/(side.length-1):0};}return {x:p.direction==='in'?-32:32,y:m.kind==='exchanger'?(p.id.endsWith('0')?-19:19):0};}
function endpoint(pg,nodeId,portId){const n=pg.nodes.find(n=>n.id===nodeId);if(!n)return null;const p=moduleOf(n).ports.find(p=>p.id===portId);if(!p)return null;const d=portOffset(n,p);const a=(n.rotation||0)*Math.PI/180;return {x:n.x+d.x*Math.cos(a)-d.y*Math.sin(a),y:n.y+d.x*Math.sin(a)+d.y*Math.cos(a),node:n,port:p};}
function routeLine(a,b){const mid=(a.x+b.x)/2;return Math.abs(a.y-b.y)<2?`M ${a.x} ${a.y} H ${b.x}`:`M ${a.x} ${a.y} H ${mid} V ${b.y} H ${b.x}`;}
// Trend-history runs (RunFrame.full=false) carry only curve variables between key frames; device
// panels and canvas readings show the most recent full row instead of blanking out.
function panelRow(run){const history=run?.history||[];for(let i=history.length-1;i>=0;i--)if(!history[i].partial)return history[i];return history.at(-1);}
function replayingKeyFrame(run){return !!run?.history?.length&&!!run.history.at(-1).partial;}
function flowFor(n){return panelRow(project().run)?.canonical?.[n.id+'.mass_flow_kg_s'] ?? null;}
const CIRCUIT_COLORS=['var(--orange)','#2f80ed','#27ae60','#9b51e0','#eb5757','#f2994a','#219653','#56ccf2'];
function circuitOfPort(key){const circuits=engine.circuits?.(project().id)||[];return circuits.length>1?circuits.find(c=>c.ports.includes(key)):null;}
function circuitLabel(c){return `回路 ${c.id+1} · ${c.fluid.fluid}${c.source==='project'?'（项目默认）':' · '+c.source}`;}
function networkMarkup(pg,mini=false){const lines=pg.edges.map(([id,a,ap,b,bp])=>{const e1=endpoint(pg,a,ap),e2=endpoint(pg,b,bp);if(!e1||!e2)return '';const d=routeLine(e1,e2),c=circuitOfPort(a+':'+ap);return `<path d="${d}" class="net-line${ui.selectedEdge===id?' selected':''}"${c?` style="stroke:${CIRCUIT_COLORS[c.id%CIRCUIT_COLORS.length]}"`:''}>${c?`<title>${esc(circuitLabel(c))}</title>`:''}</path>${mini?'':`<path d="${d}" class="net-hit" data-edge="${id}" role="button" aria-label="连接 ${a} 到 ${b}" tabindex="0"/>`}`;}).join('');
  const nodes=pg.nodes.map(n=>{const m=moduleOf(n);return `<g transform="translate(${n.x},${n.y})" class="net-node${!mini&&ui.selectedNode===n.id?' selected':''}" ${mini?'':`data-node="${n.id}" tabindex="0" role="button" aria-label="${esc(n.id+' '+n.name)}"`}><rect class="node-hit" x="-28" y="-35" width="56" height="101" fill="transparent" pointer-events="all"/><rect class="node-selection" x="-27" y="-28" width="54" height="56" rx="5"/>${portStubs(n)}${symbol(n,mini)}${mini?'':internalChannelsMarkup(n)}${!mini&&project().run.history.length&&ui.pageGrid!==null?`<text class="node-reading" x="0" y="-43" text-anchor="middle">${number(flowFor(n),3)}</text>`:''}${m.ports.map(p=>{const offset=portOffset(n,p),connected=pg.edges.some(e=>(e[1]===n.id&&e[2]===p.id)||(e[3]===n.id&&e[4]===p.id));return `<g transform="rotate(${n.rotation||0})"><g class="port-group${ui.connecting?.nodeId===n.id&&ui.connecting?.portId===p.id?' pending':''}" ${mini?'':`data-port-node="${n.id}" data-port-id="${p.id}" role="button" aria-label="${esc(n.id+' '+p.label)}" tabindex="0"`}><title>${esc(n.id+' · '+p.label+' · '+DOMAINS[p.domain].label)}${connected?' · 已连接':''}</title><circle cx="${offset.x}" cy="${offset.y}" r="${mini?3:3.5}" class="net-port${connected?' connected':''}"/>${mini?'':`<circle cx="${offset.x}" cy="${offset.y}" r="10" class="port-hit"/>`}</g></g>`;}).join('')}${mini?'':`<text class="node-code" x="0" y="44" text-anchor="middle">${esc(n.id)}</text><text class="node-name" x="0" y="60" text-anchor="middle">${esc(n.name)}</text>${quickCanvasMarkup(n,m)}`}</g>`;}).join('');return lines+nodes;}
function fluidBadge(p){const circuits=engine.circuits?.(p.id)||[];if(new Set(circuits.map(c=>c.fluid.fluid)).size>1)return `多工质 · ${circuits.length} 个回路`;const declared=new Set((p.circuitFluids||[]).map(c=>c.fluid||c.medium).filter(Boolean));if(!circuits.length&&declared.size>1)return `多工质 · ${[...declared].join(' / ')}`;return p.fluid||(MEDIA.find(m=>m[0]===p.medium)||MEDIA[0])[1];}
function renderWorkbench(){const p=project(),pg=activePage(),selected=instance(ui.selectedNode);return `<div class="workbench${ui.showLibrary?' show-library':''}${ui.showChart?' with-chart':''}"><aside class="canvas-library" id="canvas-library"><div class="library-heading"><strong>模块库</strong><small class="muted">${state.modules.length} 类</small>${ibtn('toggle-library','关闭模块库','PanelLeftClose')}</div><label class="search">${icon('Search')}<input placeholder="查找模块" aria-label="画布模块搜索" data-filter="canvasModuleSearch"></label><div class="library-scroll" id="canvas-library-list">${libraryMarkup()}</div><div class="selected-properties" id="selected-properties">${propertiesMarkup(selected)}</div></aside><div class="canvas-column"><div class="canvas-bar"><div class="canvas-pages">${pgTabs()}${ibtn('new-canvas','新增画布','Plus')}</div><div class="canvas-tools">${workflows.scenarioToolbar(p)}${coldStorage.couplingToolbar(p)}${ibtn('toggle-library',ui.showLibrary?'收起模块库':'展开模块库',ui.showLibrary?'PanelLeftClose':'PanelLeftOpen',`aria-expanded="${ui.showLibrary}" aria-controls="canvas-library"`)}${ibtn('select-mode','选择设备','MousePointer2')}${ibtn('connect-mode','连接端口','Cable')}<span class="tool-divider"></span>${ibtn('undo','撤销 Ctrl+Z','Undo2',undoStack.length?'':'disabled')}${ibtn('redo','重做 Ctrl+Y','Redo2',redoStack.length?'':'disabled')}${ibtn('fit','适应画布','Scan')}${ibtn('grid','显示点阵','Grid2X2','class="optional"')}${ibtn('validate','检查连接','ListChecks')}</div></div><div id="canvas-device-tools">${deviceToolsMarkup(selected)}</div><div class="canvas-area${ui.pageGrid?' grid':''}" id="network-area"><div class="canvas-caption"><span>${esc(pg.name)}</span><span class="muted">${p.caseId==='cold-room-ideal-v1'?'库房热平衡 · W':p.run.history.length?'质量流量 · kg/s':'单击选择 · 双击参数'}</span>${badge(p.caseId==='cold-room-ideal-v1'?'传热系统':fluidBadge(p),'blue')}</div>${pg.nodes.length?`<svg id="network" class="network-svg" viewBox="${networkViewBox(pg)}" role="group" aria-label="${esc(p.name+' '+pg.name+' 管网画布')}">${networkMarkup(pg)}</svg>`:`<div class="empty" style="padding-top:18%">${icon('Network')}<h3>在这里搭建新系统</h3><p>从左侧选择模块，再点击画布放置设备。</p>${btn('insert-defaults','放入泵阀示例','Plus','','primary')}</div><svg id="network" class="network-svg" viewBox="-35 -5 1140 510" style="position:absolute;inset:0" aria-label="空画布"></svg>`}<div class="runbar" aria-label="主系统运行控制"><button data-action="run-project" data-command="run" class="go" ${['running','solving'].includes(p.run.status)?'disabled':''}>${icon('Play')}<span>${p.run.status==='paused'?'继续':'运行'}</span></button><button data-action="run-project" data-command="pause" ${p.run.status==='running'?'':'disabled'}>${icon('Pause')}暂停</button><button data-action="run-project" data-command="step" ${['running','solving'].includes(p.run.status)?'disabled':''}>${icon('StepForward')}单步</button><button data-action="run-project" data-command="stop" ${['ready','stopped'].includes(p.run.status)?'disabled':''}>${icon('Square')}停止</button><span class="spacer"></span><button data-action="toggle-chart" aria-label="${ui.showChart?'收起同屏曲线':'展开同屏曲线'}" aria-expanded="${ui.showChart}" class="${ui.showChart?'active':''}">${icon('Activity')}曲线</button></div><div id="canvas-inspection" class="canvas-inspection" role="status" hidden></div><div class="canvas-bottom"><span data-canvas-hint>${ui.placing?'点击画布放置 '+mod(ui.placing).name:ui.connecting?'选择另一个空闲端口 · Esc 取消':'双击设备编辑参数 · 拖动空白处平移'}</span><div class="zoom">${ibtn('zoom-out','缩小','Minus')}<span>${Math.round(pg.zoom*100)}%</span>${ibtn('zoom-in','放大','Plus')}</div></div></div>${renderWorkbenchChart()}${coldStorage.markup(p)}<div class="canvas-info"><span data-result-status></span><span class="optional">${pg.nodes.length} 个设备 · ${pg.edges.length} 条连接</span><span class="push"></span>${btn('nav','项目设置','Settings2','data-route="settings"','ghost small')}${btn('nav','控制逻辑','Code2','data-route="controls"','ghost small')}</div></div><aside id="inspector-dock" aria-hidden="true"></aside></div>`;}
function pgTabs(){return project().pages.map(p=>`<button data-action="canvas-tab" data-id="${p.id}" class="${p.id===project().activePage?'active':''}">${esc(p.name)}</button>`).join('');}
function libraryMarkup(query=''){return moduleGroupNames().map(c=>{const modules=state.modules.filter(m=>m.category===c&&(m.name+m.code).toLowerCase().includes(query.toLowerCase()));return modules.length?`<div class="library-caption">${icon('ChevronDown')}${esc(c)}</div>${modules.map(m=>`<button class="library-item${ui.placing===m.id?' active':''}" data-action="place-module" data-id="${m.id}" draggable="true" data-drag-module="${m.id}">${icon(m.icon)}<span>${m.name}</span><small>${m.runtime === 'python' ? 'Python' : m.code.slice(0,2)}</small></button>`).join('')}`:'';}).join('');}
function propertiesMarkup(n){if(n){const m=moduleOf(n);return `<div class="row spread"><h3>对象属性</h3>${badge(n.id,'warn')}</div><dl><dt>名称</dt><dd>${esc(n.name)}</dd><dt>模块</dt><dd>${esc(m.name)}</dd>${m.runtime==='python'?`<dt>模块版本</dt><dd data-module-binding>v${m.version} · ${esc((m.manifest.definition_hash || m.contentHash).slice(0,12))}</dd>`:''}<dt>型号</dt><dd>${esc(model(n.modelId)?.name||'自定义参数')}</dd>${paramDefs(n).slice(0,2).map(f=>`<dt>${f[1].replace('阀门','').replace('流量系数 ','')}</dt><dd>${number(n.params[f[0]],f[0]==='opening'?0:2)} ${f[2]}</dd>`).join('')}</dl><div class="row gap-6">${btn('open-device','详细参数','SlidersHorizontal',`data-id="${n.id}"`,'small')}${ibtn('delete-node','删除选中设备','Trash2',`data-id="${n.id}"`)}</div>`;}return `<h3>画布属性</h3><dl><dt>画布</dt><dd>${esc(activePage().name)}</dd><dt>介质</dt><dd>${esc(fluidBadge(project()))}</dd><dt>选择</dt><dd>${ui.selectedEdge?'已选连接 '+esc(ui.selectedEdge):'单击设备或连接'}</dd></dl>${ui.selectedEdge?btn('delete-edge','删除连接','Trash2',`data-id="${ui.selectedEdge}"`,'small'):btn('nav','管理模块','Boxes','data-route="modules"','small ghost')}`;}
function channelFor(m,v){return m.channels.find(c=>c.enabled&&(c.input===v.port||c.output===v.port));}
function renderEditor(){const m=mod();const contents={contract:renderModuleContract,drawing:renderDrawing,attributes:renderAttributes,values:renderValues,models:renderEditorModels,code:renderCode,channels:renderChannels};return `<div class="editor-page"><header class="editor-header">${ibtn('nav','返回模块库','ChevronLeft','data-route="modules"')}${ui.editorOrigin?btn('return-device','返回 '+esc(ui.editorOrigin.nodeId)+' 设备','ArrowRight','','small'):''}<span class="object-icon">${icon(m.icon)}</span><div><h1>${esc(m.name)} <span class="muted mono" style="font-size:13px">${esc(m.code)}</span></h1><small>模块定义 · v${m.version} · ${m.ports.length} 端口 / ${m.channels.length} 通路</small></div><span class="push"></span>${badge(m.dirty?'有修改':'定义已载入',m.dirty?'warn':'')}${m.runtime === 'python' ? btn('test-module','独立验证','CheckCheck',`data-id="${m.id}"`) : ''}${btn('compile-preview','检查与调用预览','CheckCheck')}${m.runtime === 'python' ? btn('save-module-version',m.saving?'校验与试算中…':'保存新版本','Save',m.saving?'disabled':'','primary') : btn('save','保存定义','Save','','primary')}</header><nav class="tabs editor-tabs" aria-label="模块编辑页面">${[...EDITOR_TABS,...(m.runtime === 'python' ? [['contract','契约与版本','FileJson']] : [])].map(([id,label,glyph])=>`<button data-action="editor-tab" data-value="${id}" class="${ui.moduleTab===id?'active':''}" aria-current="${ui.moduleTab===id?'page':'false'}">${icon(glyph)}${label}</button>`).join('')}</nav><section class="editor-content">${(contents[ui.moduleTab]||renderDrawing)()}</section><footer class="editor-footer"><span class="row gap-6">${icon('Box')}编辑模块定义</span><span class="optional">${m.runtime === 'python' ? '项目绑定已保存版本，编辑草稿不影响项目' : '项目实例通过型号应用更新'}</span><span class="push"></span><span>${m.runtime === 'python' ? 'Python Worker · initialize → evaluate → commit_step → finalize' : '内置注册水力模型'}</span></footer></div>`;}
function drawingSVG(m){const selected=ui.editorPort;const shape=m.drawing;return `<svg id="module-drawing" viewBox="0 0 720 430" role="group" aria-label="${esc(m.name)}图形与端口"><g class="draw-object${selected==='picture'?' selected':''}" data-draw-id="picture" tabindex="0" role="button" aria-label="设备图形"><rect x="${360-shape.width*3}" y="${215-shape.height*2}" width="${shape.width*6}" height="${shape.height*4}" rx="${shape.shape==='circle'?70:8}" fill="var(--surface)" stroke="var(--blue)" stroke-width="1.6"/><text x="360" y="215" fill="var(--text)" text-anchor="middle" font-size="18">${esc(shape.label)}</text><text x="360" y="239" fill="var(--muted)" text-anchor="middle" font-size="12">${esc(m.code)}</text></g>${m.channels.filter(c=>c.enabled).map(c=>{const a=m.ports.find(p=>p.id===c.input),b=m.ports.find(p=>p.id===c.output);return a&&b?`<path d="M ${a.x*7.2} ${a.y*4.3} H ${(a.x+b.x)*3.6} V ${b.y*4.3} H ${b.x*7.2}" fill="none" stroke="var(--orange)" stroke-width="1.2" stroke-dasharray="5 4" opacity=".7"/><text x="${(a.x*.82+b.x*.18)*7.2}" y="${a.y*4.3-15}" text-anchor="middle" fill="var(--accent)" font-size="11">${esc(c.name)}</text>`:'';}).join('')}${m.ports.map(p=>`<g class="draw-object${selected===p.id?' selected':''}" data-draw-id="${p.id}" tabindex="0" role="button" aria-label="端口 ${esc(p.name)}"><rect x="${p.x*7.2-16}" y="${p.y*4.3-16}" width="32" height="32" rx="5" fill="transparent" stroke="transparent"/><circle cx="${p.x*7.2}" cy="${p.y*4.3}" r="6" fill="${p.direction==='in'?`var(--${DOMAINS[p.domain].color})`:'var(--surface)'}" stroke="var(--${DOMAINS[p.domain].color})" stroke-width="1.7"/><text x="${p.x*7.2}" y="${p.y*4.3+27}" fill="var(--text)" font-size="12" text-anchor="middle">${esc(p.name)}</text><text x="${p.x*7.2}" y="${p.y*4.3+44}" fill="var(--muted)" font-size="11" text-anchor="middle">${esc(p.label)}</text></g>`).join('')}</svg>`;}
function renderDrawing(){const m=mod(),selected=m.ports.find(p=>p.id===ui.editorPort);return `<div class="editor-drawing"><div class="draw-left"><div class="draw-toolbar"><strong>图形与端口</strong><span class="muted">拖动布置 · 方向键微调</span><span class="push"></span>${btn('editor-tab','配置内部通路','Waypoints','data-value="channels"','small')}${ibtn('draw-center','居中图形','Scan')}</div><div class="draw-board" id="draw-board">${drawingSVG(m)}</div><div class="draw-toolbar"><span class="row gap-6"><span class="port-mark in"></span>入口</span><span class="row gap-6"><span class="port-mark"></span>出口</span><span class="push muted">虚线表示设备内部通路</span></div></div><aside class="draw-sidebar"><section><h3>添加绘制对象</h3><div class="draw-palette"><button data-action="select-picture">${icon('SquareDashed')}设备图形</button><button data-action="edit-drawing-label">${icon('Pencil')}图形名称</button>${Object.entries(DOMAINS).filter(([key])=>PORT_PREFIX[key]).flatMap(([key,d])=>['in','out'].map(dir=>`<button data-action="add-port" data-domain="${key}" data-direction="${dir}"><span class="port-mark ${key} ${dir}"></span>${d.label}${dir==='in'?'输入':'输出'}</button>`)).join('')}</div><div class="notice"><span>${icon('Info')}</span><span>添加端口后，变量表会自动生成对应变量。</span></div></section><section><div class="spacer"></div><div class="row spread"><h3>对象属性</h3>${selected?ibtn('delete-port','删除选中端口','Trash2',`data-id="${selected.id}"`):''}</div><div class="stack" style="margin-top:14px">${selected?`<label class="field"><span>端口标识</span><input data-port-field="name" data-id="${selected.id}" value="${esc(selected.name)}" aria-label="端口标识"></label><label class="field"><span>中文说明</span><input data-port-field="label" data-id="${selected.id}" value="${esc(selected.label)}" aria-label="端口中文说明"></label><div class="row">${badge(DOMAINS[selected.domain].label,DOMAINS[selected.domain].color==='orange'?'warn':'blue')}${badge(selected.direction==='in'?'输入':'输出')}</div><div class="fields"><label class="field"><span>X / %</span><input type="number" min="5" max="95" data-port-field="x" data-id="${selected.id}" value="${selected.x}"></label><label class="field"><span>Y / %</span><input type="number" min="10" max="85" data-port-field="y" data-id="${selected.id}" value="${selected.y}"></label></div><small class="muted">通路：${esc(m.channels.find(c=>c.input===selected.id||c.output===selected.id)?.name||'未绑定')}</small>`:`<label class="field"><span>图形名称</span><input data-drawing-field="label" value="${esc(m.drawing.label)}" aria-label="图形名称"></label><label class="field"><span>图形形状</span><select data-drawing-field="shape">${option('rectangle','圆角矩形',m.drawing.shape)}${option('circle','椭圆',m.drawing.shape)}</select></label><div class="fields"><label class="field"><span>宽度</span><input type="number" min="15" max="60" data-drawing-field="width" value="${m.drawing.width}"></label><label class="field"><span>高度</span><input type="number" min="15" max="55" data-drawing-field="height" value="${m.drawing.height}"></label></div><small class="muted">选择端口查看编号、类型和通路。</small>`}</div></section></aside></div>`;}
function variableRows(m){return m.variables.filter(v=>(v.name+v.label+v.note).toLowerCase().includes(ui.variableSearch.toLowerCase())&&(!ui.onlyCommon||v.display)).map(v=>`<tr data-variable-row="${esc(v.id)}"><td><span class="mono">${esc(v.name)}</span><small>${esc(v.label)}</small></td><td>${v.type}</td><td>${esc(v.unit)}</td><td>${esc(m.ports.find(p=>p.id===v.port)?.name||'—')}<small>${esc(channelFor(m,v)?.name||'未绑定通路')}</small></td><td><input type="text" data-var-note="${esc(v.id)}" aria-label="${esc(v.name)} 备注" value="${esc(v.note)}" maxlength="120"></td><td><label class="check-label"><input type="checkbox" data-var-display="${esc(v.id)}" aria-label="常用变量 ${esc(v.name)}" ${v.display?'checked':''}>显示</label></td><td>${badge(v.origin==='parameter'?'参数':v.origin==='system'?'系统':v.writable?'输入':'输出',v.origin==='parameter'?'warn':'')}</td><td>${v.origin==='custom'?ibtn('delete-variable','删除变量 '+v.name,'Trash2',`data-id="${esc(v.id)}"`):'<span class="muted">—</span>'}</td></tr>`).join('');}
function renderAttributes(){const m=mod();if(m.runtime==='python')return renderPythonAttributes();return `<div class="editor-table-section"><div class="filterbar"><label class="search">${icon('Search')}<input data-filter="variableSearch" aria-label="搜索变量定义" value="${esc(ui.variableSearch)}" placeholder="变量名、中文名称或备注"></label><label class="check-label"><input type="checkbox" data-ui-toggle="onlyCommon" ${ui.onlyCommon?'checked':''}>仅常用变量</label><span class="push muted">${m.variables.length} 个变量</span>${btn('new-variable','新增变量','Plus','','primary')}</div><div class="panel table-wrap"><table class="variable-table"><thead><tr><th>变量 / 含义</th><th>类型</th><th>单位</th><th>端口 / 通路</th><th>备注</th><th>常用</th><th>属性</th><th></th></tr></thead><tbody id="variable-rows">${variableRows(m)}</tbody></table></div><section class="panel" style="margin-top:18px"><div class="panel-head"><h3>项目画布上的快捷控件</h3>${badge('由模块定义')}</div><div class="panel-body fields"><label class="field"><span>常用参数</span><select data-module-field="quickParam">${(PARAM_DEFS[m.kind]||[]).map(f=>option(f[0],f[1]+' · '+f[2],m.quickParam)).join('')||option('','暂无可调参数','')}</select></label><label class="field"><span>控件形式</span><select data-module-field="quickType">${[['slider','滑块与数值'],['switch','开关'],['number','数值输入'],['display','只读数显']].map(([k,v])=>option(k,v,m.quickType)).join('')}</select></label><div class="notice wide">${icon('Info')}<span>项目窗口优先呈现常用参数；修改模块定义后，通过型号应用更新项目实例。</span></div></div></section></div>`;}
function valueTable(m){const columns=ui.allBanks?[-1,0,1,2]:[-1,ui.bank];const vars=m.variables.filter(v=>(v.name+v.label).toLowerCase().includes(ui.valueSearch.toLowerCase()));return `<table class="value-table"><thead><tr><th>变量 / 单位</th>${columns.map(c=>`<th class="num">${c<0?'当前值':esc(m.bankNames[c])}<small style="display:block;font-weight:400">${c<0?'模块默认值':'库值 '+(c+1)}</small></th>`).join('')}</tr></thead><tbody>${vars.map(v=>`<tr><td><strong>${esc(v.label)}</strong><small><span class="mono">${esc(v.name)}</span> · ${esc(v.unit)}</small></td>${columns.map(c=>{const val=(c<0?m.values:m.banks[c])[v.id]??v.value;const diff=c>=0&&JSON.stringify(val)!==JSON.stringify(m.values[v.id]);return `<td class="num${diff?' edited':''}">${Array.isArray(val)?`<button class="array-btn" data-action="array-select" data-id="${esc(v.id)}" data-bank="${c<0?ui.bank:c}" aria-label="编辑 ${esc(v.name)} ${c<0?'当前值':'库值'+(c+1)}数组"${c<0?' disabled':''}>${val.map(n=>number(n,v.type.startsWith('int')?0:3)).join(', ')}</button>`:`<input type="number" step="${v.type==='int'?'1':'any'}" data-value-id="${esc(v.id)}" data-bank="${c}" aria-label="${esc(v.name)} ${c<0?'当前值':'库值'+(c+1)}" value="${typeof val==='number'?v.type==='int'?val:val.toFixed(m.precision):esc(val)}" ${c<0?'readonly':!v.writable?'disabled':''}>`}</td>`;}).join('')}</tr>`).join('')}</tbody></table>`;}
function bankDiff(m,index=ui.bank){return m.variables.filter(v=>v.writable&&JSON.stringify(m.values[v.id])!==JSON.stringify(m.banks[index][v.id]));}
function renderValues(){const m=mod(),array=m.variables.find(v=>v.id===ui.arrayVar&&v.type.endsWith('[8]'))||m.variables.find(v=>v.id==='system:form');const arr=m.banks[ui.bank][array.id];const form=m.banks[ui.bank]['system:form'],mix=m.banks[ui.bank]['system:mix'];return `<div class="value-layout"><section class="value-main"><div class="filterbar"><label class="search">${icon('Search')}<input data-filter="valueSearch" aria-label="查找变量值" value="${esc(ui.valueSearch)}" placeholder="查找参数或端口变量"></label><span class="push"></span><label class="check-label"><input type="checkbox" data-ui-toggle="allBanks" ${ui.allBanks?'checked':''}>三组对照</label></div><div class="row wrap spread" style="margin-bottom:14px"><div class="segmented">${[0,1,2].map(i=>`<button data-action="bank-select" data-value="${i}" class="${ui.bank===i?'active':''}">库值 ${i+1} · ${esc(m.bankNames[i])}</button>`).join('')}</div>${badge(bankDiff(m).length+' 项差异',bankDiff(m).length?'warn':'good')}</div><div class="panel table-wrap" id="value-table">${valueTable(m)}</div><div class="notice" style="margin-top:14px">${icon('Info')}<span>库值是独立的参数方案。保存保留草稿；点击“应用到当前值”后才改变模块当前值。</span></div></section><aside class="value-side"><section><h3>库值 ${ui.bank+1} · ${esc(m.bankNames[ui.bank])}</h3><label class="field"><span>方案名称</span><input data-bank-name="${ui.bank}" value="${esc(m.bankNames[ui.bank])}" maxlength="30" aria-label="库值方案名称"></label><div class="bank-direction"><span>库值 ${ui.bank+1}</span>${icon('ArrowRight')}<span>模块当前值</span></div><div class="stack" style="gap:8px">${btn('apply-bank','应用到当前值','ArrowRight','','primary')}${btn('capture-bank','当前值存入此库','Copy')}${btn('new-model','保存为设备型号','Database')}${btn('preview-design',(m.runtime==='python'?'执行设计函数 → 库值 ':'预览设计函数 ')+(ui.bank+1),'Braces','',m.runtime==='python'?'small':'ghost small')}</div><div class="spacer"></div><div class="row spread" style="margin:14px 0 10px"><h3>数组编辑</h3><span class="badge">库值 ${ui.bank+1}</span></div><label class="field"><select data-array-var aria-label="选择数组变量">${m.variables.filter(v=>v.type.endsWith('[8]')).map(v=>option(v.id,v.name,ui.arrayVar)).join('')}</select></label><div class="array-grid" style="margin-top:10px">${arr.map((v,i)=>`<label>[${i}]<input type="number" step="${array.type.startsWith('int')?'1':'any'}" data-array-index="${i}" data-id="${array.id}" aria-label="${array.name} 数组第 ${i+1} 项" value="${v}"></label>`).join('')}</div></section><section><div class="spacer"></div><h3 style="margin-top:14px">工质与质量比例</h3><div class="stack" style="gap:7px">${FLUIDS.map(([key,name,id])=>`<label class="check-label"><input type="checkbox" data-fluid-id="${id}" ${form.includes(id)?'checked':''}>${name}<small class="muted push">${id}</small></label>`).join('')}</div><div class="stack" style="gap:8px;margin-top:13px">${form.map((id,i)=>id?`<label class="mixture-row"><span>${esc(FLUIDS.find(f=>f[2]===id)?.[1]||id)}</span><input type="number" min="0" max="1" step=".01" data-mixture-index="${i}" aria-label="${esc(FLUIDS.find(f=>f[2]===id)?.[1]||id)}质量比例" value="${mix[i]}"><span></span></label>`:'').join('')}</div><div class="row spread" style="margin:14px 0"><span class="muted">合计 ${number(mix.reduce((a,b)=>a+Number(b),0),4)}</span>${btn('normalize-mixture','归一化','','','small')}</div><small class="muted">物性数据用于界面示例；此处不调用 REFPROP。</small></section></aside></div>`;}
function renderEditorModels(){const m=mod(),list=state.models.filter(v=>v.moduleId===m.id&&!v.archived);return `<div class="editor-table-section"><div class="section-title"><div><h2>${esc(m.name)}的设备型号</h2><p class="muted" style="font-size:12px;margin-top:6px">从库值保存型号，在项目中复用参数。</p></div>${btn('new-model','从库值保存型号','Plus','','primary')}</div><div class="panel table-wrap"><table><thead><tr><th>型号名称</th><th>版本</th><th>参数摘要</th><th>来源</th><th></th></tr></thead><tbody>${list.map(v=>`<tr><td><strong>${esc(v.name)}</strong><small>${esc(v.description)}</small></td><td>${badge('v'+v.version)}</td><td>${Object.entries(v.params).map(([k,val])=>`${esc((PARAM_DEFS[m.kind]||[]).find(f=>f[0]===k)?.[1]||k)} ${val}`).join(' · ')}</td><td>${esc(v.sourceLabel || "库值 " + v.bank)}</td><td>${btn('select-model','查看型号','ArrowUpRight',`data-id="${v.id}"`,'small')}</td></tr>`).join('')||'<tr><td colspan="5">暂无型号，从一组库值保存开始。</td></tr>'}</tbody></table></div><div class="concept-flow"><div class="connection-node">编辑库值<small class="muted" style="display:block">参数方案</small></div>${icon('ArrowRight')}<div class="connection-node">保存命名型号<small class="muted" style="display:block">版本与来源</small></div>${icon('ArrowRight')}<div class="connection-node">应用到项目实例<small class="muted" style="display:block">预览差异后生效</small></div></div>${btn('nav','打开完整型号库','Database','data-route="models"','ghost')}</div>`;}
function renderCodePane(kind) {
  const m=mod(), source=kind==='design'?m.source.design[ui.designIndex]:m.source[kind];
  const title={runtime:'运行代码',header:'公共代码',design:'设计函数'}[kind];
  const name=kind==='runtime'?(m.runtime==='python'?'module.py':'run.py'):kind==='header'?'common.py':`design${ui.designIndex+1}.py`;
  return `<section class="module-code-pane" data-code-pane="${kind}" aria-labelledby="code-heading-${kind}">
    <header class="code-pane-head"><h3 id="code-heading-${kind}">${icon(kind==='design'?'Braces':'FileCode2')}${title}</h3><span class="mono code-file-name">${name}</span><span class="push"></span>${btn('check-code','检查结构','CheckCheck',`data-kind="${kind}" aria-label="检查${esc(title)}结构"`,'small')}${kind==='design'?btn('preview-design','调用预览','Play',`data-index="${ui.designIndex}"`,'small'):''}</header>
    ${kind==='design'?`<label class="code-design-picker">当前函数<select data-design-select aria-label="选择设计函数">${[0,1,2].map(i=>option(i,`设计函数 ${i+1} · ${m.bankNames[i]}`,ui.designIndex)).join('')}</select></label>`:''}
    <div class="code-editor"><div class="code-lines" aria-hidden="true">${source.split('\n').map((_,i)=>i+1).join('\n')}</div><textarea spellcheck="false" wrap="off" id="${kind==='runtime'?'module-code':'module-code-'+kind}" data-code-kind="${kind}"${kind==='design'?` data-design-index="${ui.designIndex}"`:''} aria-label="${esc(title)}编辑器">${esc(source)}</textarea></div>
  </section>`;
}
const DESIGN_PLACEHOLDER = '# design.py：由一组库值计算派生参数（可选）\n# 在“变量值”页选择库值后执行；确认后才写回该库值。\n#\n# def design(ctx):\n#     d = ctx.parameter("diameter_m")\n#     ctx.set("area_m2", 3.14159 * d * d / 4)';
function renderDesignSourcePane() {
  const source=mod().designSource || '';
  return `<section class="module-code-pane" data-code-pane="design" aria-labelledby="code-heading-design-source">
    <header class="code-pane-head"><h3 id="code-heading-design-source">${icon('Braces')}设计函数</h3><span class="mono code-file-name">design.py</span><span class="push"></span>${btn('editor-tab','到变量值执行','Play','data-value="values"','small')}</header>
    <div class="code-editor"><div class="code-lines" aria-hidden="true">${source.split('\n').map((_,i)=>i+1).join('\n')}</div><textarea spellcheck="false" wrap="off" id="module-code-design" data-code-kind="design-source" aria-label="设计函数编辑器" placeholder="${esc(DESIGN_PLACEHOLDER)}">${esc(source)}</textarea></div>
  </section>`;
}
async function runDesign(bank = ui.bank) {
  const m = mod();
  if (m.runtime !== 'python') { previewDesign(bank); return; }
  if (!m.designSource?.trim()) { msg('此模块还没有 design.py，请先在“代码”页编写设计函数。', true); return; }
  if (m.designing) return;
  m.designing = true;
  try {
    const result = await engine.runDesign(m, bank);
    const applicable = result.changes.filter(c => c.variableId), skipped = result.changes.filter(c => !c.variableId);
    const notes = [...result.diagnostics.map(d => d.message), ...skipped.map(c => `${c.label} 不是数值库值，未写入`)];
    const body = diffMarkup(applicable.map(c => [c.label, c.before, c.after])) + (notes.length ? `<pre class="code-preview">${esc(notes.join('\n'))}</pre>` : '');
    openDialog(`设计函数 → 库值 ${bank + 1}`, `${m.name} · ${m.bankNames[bank]}。design.py ${result.designHash.slice(0, 12)}；确认后写入此库值，模块当前值不变。`, body, applicable.length ? () => {
      for (const c of applicable) m.banks[bank][c.variableId] = c.after;
      markDirty(m); render(); msg(`设计结果已写入库值 ${bank + 1}。`);
    } : null, '写入库值', true);
  } catch (error) { msg('设计函数执行失败：' + error.message, true); }
  finally { m.designing = false; }
}
function renderPythonAttributes() {
  const m=mod();
  return `<div class="editor-table-section stack gap-20"><div class="notice">${icon('Info')}<span>参数通过 ctx.parameter(id) 读取，计算输出通过 ctx.var(id, value) 返回；状态输出使用 state.字段名。编辑后校验并保存新版本。</span>${btn('editor-tab','完整契约','FileJson','data-value="contract"','small')}</div>
    <section class="panel"><div class="panel-head"><h2>算法参数</h2>${btn('edit-contract-item','新增参数','Plus','data-section="parameters"','primary small')}</div><div class="table-wrap"><table><thead><tr><th>标识</th><th>名称</th><th>类型</th><th>默认值 / SI</th><th>范围</th><th></th></tr></thead><tbody>${m.parameters.map(p=>`<tr><td class="mono">${esc(p.id)}</td><td>${esc(p.label)}</td><td>${esc(PARAM_TYPE_LABELS[p.value_type] || p.value_type)}</td><td>${esc(parameterValueText(p.default, p.value_type))} ${esc(p.unit?.canonical_unit || '')}</td><td>${p.value_type==='number'?`${p.minimum ?? '—'} ~ ${p.maximum ?? '—'}`:'—'}</td><td>${btn('edit-contract-item','编辑','Pencil',`data-section="parameters" data-id="${esc(p.id)}"`,'small')}</td></tr>`).join('')}</tbody></table></div></section>
    <section class="panel"><div class="panel-head"><h2>输出变量</h2>${btn('edit-contract-item','新增输出','Plus','data-section="variables"','primary small')}</div><div class="table-wrap"><table><thead><tr><th>标识</th><th>名称</th><th>来源</th><th>单位</th><th></th></tr></thead><tbody>${m.manifest.variables.filter(v=>['derived','state'].includes(v.source)).map(v=>`<tr><td class="mono">${esc(v.id)}</td><td>${esc(v.label)}</td><td>${esc(v.source)}</td><td>${esc(v.unit?.canonical_unit || '')}</td><td>${btn('edit-contract-item','编辑','Pencil',`data-section="variables" data-id="${esc(v.id)}"`,'small')}</td></tr>`).join('')}</tbody></table></div></section></div>`;
}
function editContractItem(section,id) {
  const m=mod(),spec=engine.manifestPayload(m)[section].find(p=>p.id===id) || {},parameter=section==='parameters';
  const type=spec.value_type || 'number';
  const defaultText=spec.default === undefined ? '' : type==='curve' ? JSON.stringify(spec.default) : String(spec.default);
  const unitField=field('unit','规范单位（留空表示无单位）',spec.unit?.canonical_unit || '');
  const displayFields=unitField+field('display_unit','显示单位',spec.unit?.display_unit || '')+field('display_scale','显示值到引擎值的倍率',spec.unit?.display_scale ?? 1,'type="number" step="any" required')+field('display_offset','显示偏移（显示值 = 引擎值 / 倍率 + 偏移）',spec.unit?.display_offset ?? 0,'type="number" step="any" required')+field('quantity','物理量',spec.unit?.quantity || spec.quantity || 'custom','required');
  const body=`<div class="fields">${field('id','标识',spec.id || (parameter?'gain':'gain_output'),'required maxlength="81"')}${field('label','中文名称',spec.label || '校正系数','required')}${parameter ? selectField('value_type','参数类型',[['number','数值'],['boolean','布尔'],['text','文本'],['curve','曲线']],type)+field('default','默认值（引擎单位）',defaultText,'required')+displayFields+field('display_value','显示默认值（填写后换算到引擎单位）','','type="number" step="any"')+field('minimum','最小值（引擎单位，仅数值）',spec.minimum ?? '','type="number" step="any"')+field('maximum','最大值（引擎单位，仅数值）',spec.maximum ?? '','type="number" step="any"')+selectField('runtime','允许运行中修改',[['false','否'],['true','是']],String(spec.runtime || false))+selectField('writable','参数可写',[['true','是'],['false','否']],String(spec.writable !== false)) : displayFields+selectField('source','来源',[['derived','ctx.var 计算输出'],['state','ctx.state 状态输出']],spec.source || 'derived')}</div><output id="parameter-engine-preview" class="notice"></output>`;
  const hint=parameter?'默认值按类型填写：数值写 1.5；布尔写 true 或 false；文本直接填写；曲线写 JSON 点对数组，例如 [[0, 20], [1, 10]]。':'保存到当前草稿，版本保存时由后端重新校验。四种参数类型都可在设备面板调整。';
  openDialog(parameter?'编辑参数':'编辑输出变量','保存到当前草稿，版本保存时由后端重新校验。'+hint,body,data=>{
    if(!(parameter?/^[A-Za-z][A-Za-z0-9_-]{0,80}$/:/^[A-Za-z][A-Za-z0-9_.-]{0,80}$/).test(data.id)) throw Error('标识格式不合法');
    const item={...spec,id:data.id,label:data.label};
    const unit=data.unit.trim();
    const scale=Number(data.display_scale),offset=Number(data.display_offset);
    if(!Number.isFinite(scale)||scale<=0||!Number.isFinite(offset))throw Error('单位倍率必须为有限正数，偏移必须有限。');
    item.unit=unit ? {quantity:data.quantity,canonical_unit:unit,display_unit:data.display_unit.trim() || unit,display_scale:scale,display_offset:offset} : null;
    if(parameter) {
      item.value_type=data.value_type;
      item.runtime=data.runtime==='true';item.writable=data.writable==='true';
      if(item.runtime&&!item.writable)throw Error('运行中修改需要参数可写。');
      if(data.value_type==='number') {
        item.minimum=data.minimum===''?null:Number(data.minimum);item.maximum=data.maximum===''?null:Number(data.maximum);
        if(item.minimum!==null && item.maximum!==null && item.minimum>item.maximum) throw Error('最小值不能大于最大值');
        const engineDefault=data.display_value!=='' ? (Number(data.display_value)-offset)*scale : Number(data.default);
        item.default=numeric(engineDefault,item.minimum ?? -1e12,item.maximum ?? 1e12);
      } else {
        item.minimum=null;item.maximum=null;item.unit=null;
        if(data.value_type==='boolean') { const text=String(data.default).trim().toLowerCase(); if(!['true','false'].includes(text)) throw Error('布尔默认值只能是 true 或 false'); item.default=text==='true'; }
        else if(data.value_type==='text') item.default=data.default;
        else item.default=parseCurveDraft(data.default);
      }
    } else { item.source=data.source;item.quantity=data.quantity;if(item.source==='state' && !item.id.startsWith('state.')) throw Error('状态输出标识应为 state.字段名'); }
    engine.updateContractItem(m,section,id,item);
  },'应用到草稿');
}
document.addEventListener('input',event=>{
  const form=event.target.closest('#dialog-form'),output=form?.querySelector('#parameter-engine-preview');
  if(!output)return;
  const fields=Object.fromEntries(new FormData(form)),value=fields.display_value!=='' && fields.display_value!==undefined ? (Number(fields.display_value)-Number(fields.display_offset))*Number(fields.display_scale) : Number(fields.default);
  output.textContent=Number.isFinite(value)?`引擎默认值预览：${value} ${fields.unit || ''}`:'请输入有效的显示值与单位换算。';
});
function renderModuleContract() {
  const m=mod();
  if(m.runtime!=='python') return '<div class="notice">请选择 Python 模块。</div>';
  const release=m.publishedManifest;
  return `<div class="editor-table-section stack gap-20">
    <section class="panel"><div class="panel-head"><h2>模块契约</h2>${badge(release ? '已保存 v'+release.version : '未保存版本',release?'good':'warn')}</div>
      <div class="panel-body stack"><div class="row spread"><span class="mono">${esc(m.id)} · ${esc(m.entrypoint)}</span>${btn('validate-module-contract','校验并应用契约','CheckCheck','','primary')}</div>
      <p class="muted">编辑参数默认值与范围、端口、通路和输出变量。数值、布尔、文本和曲线参数都可以在设备面板按类型调整。契约使用 SI 单位，显示换算由 unit 定义。</p>
      <div class="notice">${icon('Info')}<span>编辑 JSON 后点击“校验并应用契约”同步到图形和参数面板。保存版本会重新校验当前契约及代码，并使用参数默认值进行独立试算。</span></div>
      <textarea data-module-contract aria-label="模块契约 JSON" spellcheck="false" style="width:100%;min-height:440px;font-family:monospace;line-height:1.6;white-space:pre;tab-size:2">${esc(engine.contractText(m))}</textarea>
      <label class="field"><span>版本备注</span><textarea data-release-notes aria-label="版本备注" maxlength="2000" rows="2" placeholder="说明算法、参数或端口的变化">${esc(m.releaseNotes || '')}</textarea></label>
      <pre id="module-output" class="code-output" role="status" style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(m.authoringOutput || '尚未校验。保存后按模块 ID 自动递增版本，旧版本永久保留。')}</pre>${renderAuthoringDiagnostics(m)}</div></section>
    <section class="panel"><div class="panel-head"><h2>后端版本记录</h2>${btn('module-versions','刷新版本','RefreshCw','','small')}</div><div class="table-wrap"><table><thead><tr><th>版本</th><th>保存时间</th><th>备注与契约哈希</th><th>验证</th><th></th></tr></thead><tbody>${(m.versions || []).map(v=>`<tr><td>v${esc(v.package.version)}</td><td>${esc(v.created_at ? new Date(v.created_at).toLocaleString() : '内置示例')}</td><td>${esc(v.release_notes || '—')}<small class="mono" title="${esc(v.package.definition_hash || v.package.content_hash)}">${esc((v.package.definition_hash || v.package.content_hash).slice(0,16))}</small></td><td>${v.tested?'Worker 试算通过':'示例包'}</td><td>${btn('load-module-version','载入为草稿','History',`data-version="${Number(v.package.version.split('.')[0])}"`,'small')}</td></tr>`).join('') || '<tr><td colspan="5">点击刷新读取版本记录；尚未保存的新模块没有版本。</td></tr>'}</tbody></table></div></section>
  </div>`;
}
function renderCode() {
  const variables=mod().variables.filter(v=>v.origin==='parameter'||v.display);
  if (mod().runtime === 'python') return `<div class="module-code-page"><div class="notice">${icon('Info')}<span>module.py：编辑四阶段生命周期。design.py：可选，由库值计算派生参数，随版本保存。参数、端口和输出变量在“契约与版本”中定义。</span>${btn('editor-tab','契约与版本','FileJson','data-value="contract"','small')}</div><div class="module-code-grid python">${renderCodePane('runtime')}${renderDesignSourcePane()}</div><pre class="code-output" role="status" id="code-output">${esc(mod().authoringOutput || '尚未校验。检查结构将调用后端语法与入口校验。')}</pre>${renderAuthoringDiagnostics(mod())}</div>`;
  return `<div class="module-code-page">
    <div class="module-code-tools"><label>插入位置<select data-code-target aria-label="变量插入位置">${[['runtime','运行代码'],['header','公共代码'],['design','当前设计函数']].map(([key,label])=>option(key,label,ui.codeKind)).join('')}</select></label><label class="code-variable-picker">变量<select data-code-variable aria-label="选择插入变量" ${variables.length?'':'disabled'}>${variables.map(v=>option(v.name,`${v.name} · ${v.label}`,ui.codeVariable||variables[0]?.name)).join('')||option('','无可用变量','')}</select></label>${btn('insert-code-variable','插入到光标','Plus',variables.length?'':'disabled','small')}<span class="push muted">Python</span></div>
    <div class="module-code-grid">${renderCodePane('runtime')}${renderCodePane('header')}${renderCodePane('design')}</div>
    <div class="code-output" role="status" id="code-output"><strong>检查与调用输出</strong>\n${esc(ui.compileOutput)}</div>
  </div>`;
}
function renderAuthoringDiagnostics(m) {
  return `<div id="authoring-diagnostics" class="stack">${(m.authoringDiagnostics || []).map(d=>`<div class="row">${d.source_line ? btn('module-error-line',`${d.source_file || 'module.py'}:${d.source_line}`,'ArrowRight',`data-line="${d.source_line}" data-file="${esc(d.source_file || 'module.py')}"`,'small') : ''}<span>${esc(d.message)}${d.occurrences > 1 ? ` ×${d.occurrences}` : ''}</span></div>`).join('')}${m.authoringReplay ? btn('export-module-replay','导出错误重放输入','Download','','small') : ''}${m.manifest?.composite ? btn('view-composite','查看组合展开','Network','','small') : ''}${btn('configure-module-tests','配置工况与预期值','Settings2','','small')}${btn('module-test-suite','运行测试组合','ListChecks',ui.moduleSuiteAbort?'disabled':'','small')}${btn('cancel-module-suite','取消测试','Square',ui.moduleSuiteAbort?'':'disabled','small')}</div>`;
}
function configureAuthoringSuite(m) {
  const definition=engine.manifestPayload(m);
  let editor;
  openDialog('模块测试组合','为每个工况设置边界、参数和结果预期。配置随工作区保存。', '<div id="module-suite-editor"></div>',()=>{
    m.authoringTestCases=editor.read();m.authoringOutput='测试配置已更新，请运行测试组合。';m.authoringDiagnostics=[];
    markDirty();render();
  },'保存测试配置',true);
  editor=window.ModuleTestEditor.mount(document.getElementById('module-suite-editor'),window.ModuleTestEditor.cases(m,definition),definition);
}
function moduleEvidenceSummary(m) {
  const definition=m.publishedManifest || m.manifest;
  if(!definition)return '';
  const records=(m.manifest?.validation_evidence || m.versions?.[0]?.validation_evidence || []).filter(e=>e.definition_hash===definition.definition_hash && e.content_hash===definition.content_hash);
  const names={L1:'接口',L2:'单模块逻辑',L3:'网络',L4:'独立解析',external:'外部标定'};
  const evidence=records.length?records.map(e=>`${names[e.level]}${e.status==='passed'?'验证通过':e.status==='failed'?'验证失败':'待数据'}`).join(' · '):'验证证据未登记';
  const scope=definition.applicability;
  return `<p class="muted">${esc((m.dirty?'发布版本：':'')+evidence)}${scope?`<br>${esc(scope.phases.join('／')+'；'+scope.assumptions.join('；'))}`:''}</p>`;
}
async function runAuthoringSuite(m) {
  ui.moduleSuiteAbort?.abort();
  const controller=new AbortController(); ui.moduleSuiteAbort=controller;
  const definition=engine.manifestPayload(m), before=JSON.stringify(definition);
  const cases=window.ModuleTestEditor.cases(m,definition), casesBefore=JSON.stringify(cases);
  m.authoringOutput=`正在执行 ${cases.length} 个工况及预期值检查…`;render();
  try {
    const response=await fetch('/api/v1/modules/test-suite',{method:'POST',headers:{'Content-Type':'application/json',...engine.authHeaders()},body:JSON.stringify({module:definition,cases}),signal:controller.signal});
    const data=await response.json(); if(!response.ok)throw Error(data.detail?.message || JSON.stringify(data.detail));
    if(before!==JSON.stringify(engine.manifestPayload(m)) || casesBefore!==JSON.stringify(window.ModuleTestEditor.cases(m,definition)))throw Error('测试期间草稿或测试配置已变化，请重新验证。');
    m.authoringDiagnostics=data.cases.flatMap(c=>c.diagnostics);
    m.authoringOutput=window.ModuleTestEditor.summary(data);
  } catch(error){m.authoringOutput=error.name==='AbortError'?'测试已取消，草稿已保留。':'测试失败：'+error.message;}
  finally{if(ui.moduleSuiteAbort===controller){ui.moduleSuiteAbort=null;render();}}
}
function renderChannels(){const m=mod();const first=m.channels[0],a=m.ports.find(p=>p.id===first?.input),b=m.ports.find(p=>p.id===first?.output);return `<div class="editor-table-section"><div class="section-title"><div><h2>定义设备内部通路</h2><p class="muted" style="font-size:12px;margin-top:6px">将同一物理通道的入口与出口关联；变量的通道列随绑定更新。</p></div>${btn('add-channel','新增通路','Plus','','primary')}</div><div class="panel table-wrap"><table class="channel-table"><thead><tr><th>通路名称</th><th>入口</th><th>出口</th><th>关系类型</th><th>启用</th><th></th></tr></thead><tbody>${m.channels.map(c=>`<tr><td><input class="cell-input" data-channel-id="${c.id}" data-channel-field="name" aria-label="${c.id} 通路名称" value="${esc(c.name)}"></td><td><select data-channel-id="${c.id}" data-channel-field="input" aria-label="${c.id} 入口">${option('','选择入口',c.input)}${m.ports.filter(p=>p.direction==='in').map(p=>option(p.id,p.name+' · '+p.label,c.input)).join('')}</select></td><td><select data-channel-id="${c.id}" data-channel-field="output" aria-label="${c.id} 出口">${option('','选择出口',c.output)}${m.ports.filter(p=>p.direction==='out').map(p=>option(p.id,p.name+' · '+p.label,c.output)).join('')}</select></td><td><select data-channel-id="${c.id}" data-channel-field="kind" aria-label="${c.id} 关系类型">${[['resistance','阻力关系'],['pressure','压差关系'],['flow','指定流量'],['signal','信号映射']].map(([k,v])=>option(k,v,c.kind)).join('')}</select></td><td><label class="check-label"><input type="checkbox" data-channel-id="${c.id}" data-channel-field="enabled" aria-label="启用 ${c.name}" ${c.enabled?'checked':''}>启用</label></td><td>${ibtn('delete-channel','删除 '+c.name,'Trash2',`data-id="${c.id}"`)}</td></tr>`).join('')||'<tr><td colspan="6">此模块尚未设置内部通路。</td></tr>'}</tbody></table></div><div class="row spread" style="margin:14px 0 20px"><small class="muted">类型相同的端口才能组成通路；每个端口只绑定一条启用通路。</small>${btn('check-channels','检查通路','ListChecks','','small')}</div><div id="channel-feedback"></div><div class="channel-diagram"><div class="stack" style="gap:5px;text-align:center"><span class="mono">${a?esc(a.name):'入口'}</span><small class="muted">${a?esc(a.label):'选择端口'}</small></div><span class="channel-link"></span><div class="channel-box"><strong>${esc(m.name)}</strong><small class="muted" style="display:block;margin-top:4px">${first?esc(first.name):'内部关系'}</small></div><span class="channel-link"></span><div class="stack" style="gap:5px;text-align:center"><span class="mono">${b?esc(b.name):'出口'}</span><small class="muted">${b?esc(b.label):'选择端口'}</small></div></div></div>`;}
function renderNodesPage(){const domain=DOMAINS[ui.nodeDomain];return `<div class="page-shell">${heading('节点与端口定义','按物理类型组织接口，明确变量含义与连接规则。',btn('nav','返回模块库','ChevronLeft','data-route="modules"'))}<div class="split-view"><aside class="side-nav"><div class="side-caption">接口领域</div>${Object.entries(DOMAINS).map(([k,d])=>`<button data-action="node-domain" data-value="${k}" class="${k===ui.nodeDomain?'active':''}">${icon(d.icon)}${d.label}端口</button>`).join('')}</aside><div class="stack"><section class="panel"><div class="panel-head"><div class="row"><span class="object-icon">${icon(domain.icon)}</span><div><h2>${domain.label}端口</h2><small class="muted">${ui.nodeDomain==='fluid'?'状态量、流量与工质组成':'接口与变量定义示例'}</small></div></div>${badge(ui.nodeDomain==='fluid'?'液态水场景':'接口预留',ui.nodeDomain==='fluid'?'good':'warn')}</div><div class="table-wrap"><table><thead><tr><th>变量后缀</th><th>中文名称</th><th>单位</th><th>说明</th></tr></thead><tbody>${(ui.nodeDomain==='fluid'?[['FLOW','质量流量','kg/s','沿端口约定方向记录，可表达反向流动'],['PRE','绝对压力','MPa','与求解器约定之间显式换算'],['ENTHALPY','比焓','kJ/kg','能量输运状态量'],['TEMP','温度','°C','工程显示单位'],['VOLUME','密度','kg/m³','参考命名对应密度，不能当作比容'],['Q','干度','—','相态描述；当前水网范围不扩展两相求解'],['X','质量组分','—','与 FORM 工质顺序对应']]:ui.nodeDomain==='info'?[['VALUE','信号数值','自定义','根据物理量定义单位'],['QUALITY','数据质量','—','有效、过期或缺失状态']]:ui.nodeDomain==='power'?[['VOLTAGE','电压','V','电气接口的定义示例'],['CURRENT','电流','A','当前原型不提供电网计算']]:[['SPEED','转速','r/min','机械接口的定义示例'],['TORQUE','转矩','N·m','当前原型不提供机械求解']]).map(row=>`<tr>${row.map((v,i)=>`<td${i===0?' class="mono"':''}>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section><section class="panel"><div class="panel-head"><h3>连接规则</h3></div><div class="panel-body stack"><div class="row">${icon('CheckCircle2')}同一内部通路的两端类型一致</div><div class="row">${icon('CheckCircle2')}端口拥有稳定标识，显示名称可以独立编辑</div><div class="row">${icon('CheckCircle2')}一个项目端口对应一条连接，分支使用连接节点</div><div class="row">${icon('CheckCircle2')}类型与单位定义供变量表、图形、型号和曲线共用</div></div></section>${btn('edit-module','在模块中配置端口','ArrowRight',`data-id="${ui.nodeDomain==='fluid'?'valve':'pid'}"`,'primary')}</div></div></div>`;}
function renderModels(){let models=state.models.filter(m=>(ui.modelFilter==='archived'?m.archived:!m.archived)&&(m.name+mod(m.moduleId).name).toLowerCase().includes(ui.modelSearch.toLowerCase()));const selected=models.find(m=>m.id===state.selectedModel)||models[0];return `<div class="page-shell">${heading('设备型号库','从已验证的参数形成型号；项目实例保留自己的参数与来源版本。',btn('new-model','保存新型号','Plus','','primary'))}<div class="filterbar"><label class="search">${icon('Search')}<input data-filter="modelSearch" aria-label="搜索型号" placeholder="型号名称或模块名称" value="${esc(ui.modelSearch)}"></label><div class="segmented">${[['all','在用型号'],['archived','已归档']].map(([k,v])=>`<button data-action="model-filter" data-value="${k}" class="${ui.modelFilter===k?'active':''}">${v}</button>`).join('')}</div><span class="push muted">${models.length} 个型号</span>${btn('export','导出型号库','Download','data-format="models"','small')}</div><div class="model-layout"><section class="panel"><div class="table-wrap"><table><thead><tr><th>型号名称</th><th>所属模块</th><th>版本</th><th>主要参数</th><th></th></tr></thead><tbody>${models.map(m=>`<tr class="${m.id===selected?.id?'model-selected':''}"><td><button data-action="focus-model" data-id="${m.id}" style="text-align:left;padding:0"><strong>${esc(m.name)}</strong><small>${esc(m.description)}</small></button></td><td>${esc(mod(m.moduleId).name)}</td><td>${badge('v'+m.version)}</td><td>${Object.entries(m.params).slice(0,2).map(([k,v])=>`<span class="mono">${v}</span> ${(PARAM_DEFS[mod(m.moduleId).kind]||[]).find(f=>f[0]===k)?.[2]||''}`).join(' · ')}</td><td>${ibtn('focus-model','查看型号 '+m.name,'ChevronRight',`data-id="${m.id}"`)}</td></tr>`).join('')||'<tr><td colspan="5">没有匹配的型号。</td></tr>'}</tbody></table></div></section>${selected?`<aside class="model-detail stack"><section class="panel"><div class="panel-head"><div><h2>${esc(selected.name)}</h2><small class="muted">${esc(mod(selected.moduleId).name)} · v${selected.version}</small></div>${icon('Database')}</div><div class="panel-body stack"><p class="muted" style="font-size:12px">${esc(selected.description)}</p><div class="fields">${Object.entries(selected.params).map(([key,val])=>{const f=(PARAM_DEFS[mod(selected.moduleId).kind]||[]).find(f=>f[0]===key);return `<div class="field"><span>${esc(f?.[1]||key)}</span><strong>${number(val,f?.[0]==='opening'?0:2)} <small class="muted">${f?.[2]||''}</small></strong></div>`;}).join('')}</div>${modelVariableSummary(selected)}<div class="spacer"></div>${btn('insert-model','插入当前项目','Plus',`data-id="${selected.id}"`,'primary')}${btn('apply-model-to-instance','应用到已有设备','GitCompareArrows',`data-id="${selected.id}"`)}<div class="row">${btn('edit-model','保存新版本','Pencil',`data-id="${selected.id}"`,'small')}${btn('archive-model',selected.archived?'恢复型号':'归档型号','History',`data-id="${selected.id}"`,'ghost small')}</div><small class="muted">更新型号不会自动改动已插入的实例。</small></div></section><section class="panel"><div class="panel-head"><h3>版本记录</h3>${badge(selected.versions.length+' 个版本')}</div><div class="panel-body">${selected.versions.slice().reverse().map(v=>`<div class="version-item"><span class="object-icon" style="width:26px;height:26px">${icon('History')}</span><div class="grow"><strong>v${v.version}</strong><small>${esc(v.note)}</small></div>${v.version===selected.version?badge('当前'):btn('model-version','对照','','data-version="'+v.version+'" data-id="'+selected.id+'"','small')}</div>`).join('')}</div></section></aside>`:''}</div></div>`;}
function benchParamFields(m, b) {
  const locked = ['running','solving'].includes(b.run.status) ? 'disabled' : '';
  const numeric = (PARAM_DEFS[m.kind] || []).map(f => `<label class="field"><span>${esc(f[1])}</span><div class="field-unit"><input type="number" data-bench-param="${esc(f[0])}" min="${f[3]}" max="${f[4]}" step="${f[5]}" value="${b.params[f[0]] ?? f[6]}" ${locked}><span>${esc(f[2])}</span></div></label>`).join('');
  const extra = manifestParamSpecs(m.manifest).filter(p => p.value_type !== 'number').map(p => {
    const value = b.params[p.id], text = parameterValueText(value, p.value_type);
    const input = p.value_type === 'boolean'
      ? `<label class="check-label"><input type="checkbox" data-bench-param="${esc(p.id)}" data-param-type="boolean" ${value === true ? 'checked' : ''} ${locked}>启用</label>`
      : p.value_type === 'curve'
        ? `<textarea class="cell-input mono" rows="3" data-bench-param="${esc(p.id)}" data-param-type="curve" ${locked}>${esc(text)}</textarea>`
        : `<input type="text" data-bench-param="${esc(p.id)}" data-param-type="text" value="${esc(text)}" maxlength="200" ${locked}>`;
    return `<label class="field"><span>${esc(p.label)} · ${esc(PARAM_TYPE_LABELS[p.value_type] || p.value_type)}</span>${input}</label>`;
  }).join('');
  return numeric + extra;
}
function renderBench(){const b=state.bench,m=mod(b.moduleId),run=b.run;return `<div class="page-shell">${heading('独立验证台','用独立边界与参数检查设备；测试不会改变项目实例。',btn('edit-module','编辑模块','Pencil',`data-id="${m.id}"`)+btn('save','保存测试配置','Save'))}<div class="bench-layout"><aside class="stack"><section class="panel"><div class="panel-head"><h3>被测设备</h3>${badge(m.runtime === 'python' ? 'Python Worker · v'+m.version : '请选择 Python 模块','blue')}</div><div class="panel-body stack"><label class="field"><span>模块</span><select data-bench-module aria-label="选择被测模块" ${['running','solving'].includes(run.status)?'disabled':''}>${state.modules.filter(x=>x.runtime === 'python').map(x=>option(x.id,x.name,m.id)).join('')}</select></label>${benchParamFields(m, b)}<small class="muted">参数仅用于此测试副本。</small></div></section><section class="panel"><div class="panel-head"><h3>边界条件</h3></div><div class="panel-body stack">${[['inlet','入口压力','kPa'],['outlet','出口压力','kPa'],['temperature','入口温度','°C']].map(([key,label,unit])=>`<label class="field"><span>${label}</span><div class="field-unit"><input type="number" data-bench-boundary="${key}" step="any" value="${b.boundary[key]}" aria-label="测试${label}" ${['running','solving'].includes(run.status)?'disabled':''}><span>${unit}</span></div></label>`).join('')}<label class="field"><span>时间步长</span><div class="field-unit"><input type="number" data-bench-step ${['running','solving'].includes(run.status)?'disabled':''} value="${run.step}" min=".01" max="10" step=".01"><span>s</span></div></label></div></section></aside><section class="panel"><div class="run-control"><div class="runtime"><span class="dot" style="color:var(--green)"></span><strong>${m.name} · ${statusText(run)}</strong><span class="mono" data-bench-time>${clockLabel(run.time)}</span></div><span class="push"></span>${runControls('bench',run)}</div><div class="bench-schematic"><svg viewBox="0 0 780 180" role="img" aria-label="独立边界与被测设备"><path d="M 145 80 H 620" class="net-line"/><circle cx="145" cy="80" r="25" fill="var(--blue-soft)" stroke="var(--blue)"/><circle cx="620" cy="80" r="25" fill="var(--blue-soft)" stroke="var(--blue)"/><rect x="300" y="48" width="165" height="65" rx="7" fill="var(--surface)" stroke="var(--orange)"/><text x="382" y="84" text-anchor="middle" fill="var(--text)" font-size="15">${esc(m.name)}</text><text x="145" y="85" text-anchor="middle" fill="var(--blue)" font-size="14">P</text><text x="620" y="85" text-anchor="middle" fill="var(--blue)" font-size="14">P</text><text x="145" y="136" text-anchor="middle" fill="var(--muted)" font-size="12">${b.boundary.inlet} kPa</text><text x="620" y="136" text-anchor="middle" fill="var(--muted)" font-size="12">${b.boundary.outlet} kPa</text><text x="382" y="150" text-anchor="middle" fill="var(--muted)" font-size="11">独立网络 · Worker 实际求解</text></svg></div><div class="tabs">${[['results','运行结果'],['curves','趋势曲线'],['events','事件记录']].map(([k,v])=>`<button data-action="bench-tab" data-value="${k}" class="${ui.benchTab===k?'active':''}">${v}</button>`).join('')}</div><div id="bench-results">${benchResults()}</div></section></div></div>`;}
function runControls(scope,run){return `${btn(scope==='bench'?'run-bench':'run-project',run.status==='paused'?'继续':'运行','Play',`data-command="run" ${['running','solving'].includes(run.status)?'disabled':''}`,'run small')}${btn(scope==='bench'?'run-bench':'run-project','暂停','Pause',`data-command="pause" ${run.status==='running'?'':'disabled'}`,'small')}${btn(scope==='bench'?'run-bench':'run-project','单步','StepForward',`data-command="step" ${['running','solving'].includes(run.status)?'disabled':''}`,'small')}${btn(scope==='bench'?'run-bench':'run-project','停止','Square',`data-command="stop" ${['ready','stopped'].includes(run.status)?'disabled':''}`,'small')}`;}
function benchResults() {
  const b=state.bench,run=b.run,v=run.values,worker=run.worker,m=mod(b.moduleId);
  const benchChannels=(m.manifest?.channels || []).filter(c => c.enabled !== false);
  if (ui.benchTab === 'events') return `<div class="panel-body"><div class="notice">${icon('Info')}显示 Worker 生命周期与后端诊断。</div><div class="log-list">${run.events.slice().reverse().map(e=>`<div class="log-line"><time>${number(e.t,2)} s</time><span>${esc(e.text)}</span></div>`).join('') || empty('还没有测试事件','选择 Python 模块包后运行。')}</div></div>`;
  const table=(title,items)=>`<div class="panel-head"><h3>${title}</h3></div><div class="table-wrap"><table><thead><tr><th>字段</th><th>值</th></tr></thead><tbody>${Object.entries(items || {}).map(([key,value])=>`<tr><td class="mono">${esc(key)}</td><td class="mono">${esc(typeof value === 'object' ? JSON.stringify(value) : value)}</td></tr>`).join('') || '<tr><td colspan="2">尚无返回值</td></tr>'}</tbody></table></div>`;
  return `<div class="metric-row"><div class="metric"><span>${benchChannels.length > 1 ? '通路合计流量' : '质量流量'}</span><strong data-bench-q>${number(run.history.length ? v.q : null,4)}</strong><small>kg/s · ${benchChannels.length || 1} 条通路</small></div><div class="metric"><span>边界压差</span><strong>${number(b.boundary.inlet-b.boundary.outlet,2)}</strong><small>kPa</small></div><div class="metric"><span>提交次数</span><strong data-bench-commits>${worker ? number(worker.committed.state.commit_count,0) : '—'}</strong><small>commit_step</small></div></div>
  <div class="chart-panel"><div class="chart-heading"><h3>独立网络流量</h3><span class="push"></span>${badge(worker ? 'Worker 已完成 · v'+worker.version : '等待测试',worker ? 'good' : '')}</div>${chartSvg(run.history,['q'],'bench-chart')}<div class="chart-readout" id="bench-chart-readout">${clockLabel(run.time)} · ${esc(mod(b.moduleId).name)}</div></div>
  ${ui.benchTab === 'results' ? table('evaluate 变量与物性',worker?.evaluation.variables) + table('commit_step 状态',worker?.committed.state) + table('网络关系',Object.fromEntries((worker?.evaluation.relations || []).map(r=>[r.channel,{kind:r.kind,...r.parameters}]))) : ''}
  <div class="panel-body stack"><small class="muted mono" style="overflow-wrap:anywhere">${worker ? '内容哈希：'+esc(worker.contentHash) : '运行后返回实际求解流量、模块变量和状态。'}</small><div>${btn('record-bench','保存测试记录','Save','','small')}</div></div>`;
}
function currentChartRun(){if(state.charts.source!=='live')return state.records.find(r=>r.id===state.charts.source)||project().run;const run=project().run,overview=state.charts.range==='all'&&run.source==='engine'?engine.overview(run.id):null;return overview?.rows?{...run,history:overview.rows}:run;}
function renderCurves(){const run=currentChartRun(),history=run.history;return `<div class="page-shell">${heading('曲线与工况对照','从设备变量加入曲线，跟随运行、暂停和单步观察变化。',btn('add-chart-variable','添加观察变量','Plus','','primary')+btn('export','导出曲线','Download','data-format="csv"'))}${workflows.comparisonMarkup()}<div class="filterbar"><label class="field" style="flex-direction:row;align-items:center"><span>数据来源</span><select data-chart-source aria-label="曲线数据来源">${option('live','当前主系统 · '+project().name,state.charts.source)}${state.records.filter(r=>r.history.length).map(r=>option(r.id,r.name+(r.sample?' · 演示记录':' · 计算记录'),state.charts.source)).join('')}</select></label>${state.charts.source==='live'?`<label class="field" style="flex-direction:row;align-items:center"><span>时间范围</span><select data-chart-range aria-label="曲线时间范围">${option('window','最近 2001 帧',state.charts.range)}${option('all','全程（抽稀）',state.charts.range)}</select></label>`:''}<label class="check-label"><input type="checkbox" data-chart-compare ${state.charts.compare?'checked':''}>叠加最近保存的真实工况</label><span class="push"></span>${state.charts.source==='live'?runControls('project',project().run):badge('历史记录','blue')}</div><div class="chart-grid-layout"><section class="panel"><div class="chart-panel"><div class="chart-heading"><h2>管网流量</h2><span class="muted">${esc(state.charts.source==='live'?project().name:run.projectName)}</span><span class="push"></span><div class="chart-legend">${['q','a','b'].map(k=>`<button data-action="toggle-series" data-value="${k}" class="${state.charts.series[k]?'':'off'}" aria-pressed="${state.charts.series[k]}"><span class="series-key ${SERIES[k].color}"></span>${SERIES[k].short}</button>`).join('')}${state.charts.compare?'<span class="muted">┄ 额定基准</span>':''}</div></div><div id="main-chart">${chartSvg(history,['q','a','b'],'main-flow-chart',state.charts.compare)}</div><div class="chart-readout" id="main-flow-chart-readout">${history.length?`${clockLabel(history.at(-1).t)} · 主管 ${number(history.at(-1).q,3)} kg/s`:'还没有当前运行数据。可以运行、单步，或切换到示例历史记录。'}</div></div><div class="chart-variable-list"><span class="badge">P1 · 出口流量</span><span class="badge">V1 · 出口流量</span><span class="badge">V2 · 出口流量</span>${chartBindingsForRun(run).map(v=>`<span class="badge blue">${esc(v.label)}${state.charts.source==='live'?`<button data-action="remove-chart-var" data-id="${esc(v.id)}" aria-label="移除 ${esc(v.label)}">${icon('X')}</button>`:''}</span>`).join('')}</div></section><section class="panel"><div class="chart-panel"><div class="chart-heading"><h3>出口压力</h3><span class="push muted">P1 · kPa</span></div><div id="pressure-chart">${chartSvg(history,['pressure'],'pressure-line')}</div><div class="chart-readout" id="pressure-line-readout">${badge('后端水力结果')}</div></div></section><section class="panel"><div class="chart-panel"><div class="chart-heading"><h3>出口温度（热力算法未接入）</h3><span class="push muted">P1 · °C</span></div><div id="temperature-chart">${chartSvg(history,['temperature'],'temperature-line')}</div><div class="chart-readout" id="temperature-line-readout">${badge('后端水力结果')}</div></div></section></div><div id="extra-charts" class="chart-grid-layout" style="margin-top:18px">${extraChartsMarkup()}</div>${run.events?.length?`<section class="panel" style="margin-top:18px"><div class="panel-head"><h3>本次运行事件</h3></div><div class="log-list">${run.events.slice(-5).map(e=>`<div class="log-line"><time>${number(e.t,1)} s</time><span>${esc(e.text)}</span></div>`).join('')}</div></section>`:''}</div>`;}
function renderRuns(){
  const list=state.records.filter(r=>ui.runFilter==='all'||r.status===ui.runFilter), selected=list.find(r=>r.id===ui.selectedRecord)||list[0];
  return `<div class="page-shell">${heading('运行记录','服务端自动归档最近 20 次结束运行；长运行保留最近窗口与全程抽稀曲线。',btn('refresh-archives','刷新档案','RefreshCw')+btn('record-project','记录当前运行','Save'))}
  <section class="panel"><div class="panel-head"><h2>服务端档案</h2></div><div class="panel-body">${(ui.archivedRuns||[]).map(r=>`<div class="row spread" style="margin-bottom:8px"><span>${esc(r.name)} · ${esc(r.status)} · ${number(r.time_s,1)} s</span><span class="row">${btn('open-archive','查看档案','FolderOpen',`data-id="${esc(r.id)}"`,'small')}${['completed','failed','cancelled','interrupted'].includes(r.status)?btn('delete-archive','删除','Trash2',`data-id="${esc(r.id)}"`,'small'):''}</span></div>`).join('')||'<p class="muted">暂无服务端档案。</p>'}</div></section>
  <div class="filterbar"><div class="segmented">${[['all','全部记录'],['completed','已完成'],['failed','失败记录']].map(([k,v])=>`<button data-action="run-filter" data-value="${k}" class="${ui.runFilter===k?'active':''}">${v}</button>`).join('')}</div><span class="push muted">${list.length} 条已载入记录</span></div>
  <div class="model-layout"><section class="panel table-wrap"><table><thead><tr><th>记录名称 / 来源</th><th>模式</th><th>仿真时间</th><th>状态</th><th></th></tr></thead><tbody>${list.map(r=>`<tr><td><button data-action="select-record" data-id="${r.id}"><strong>${esc(r.name)}</strong><small>${esc(r.projectName)} · ${esc(r.id)}</small></button></td><td>${esc(r.mode)}</td><td>${number(r.time,1)} s</td><td>${esc(r.status)}</td><td>${ibtn('select-record','查看运行记录','ChevronRight',`data-id="${r.id}"`)}</td></tr>`).join('')||'<tr><td colspan="5">点击服务端档案以载入曲线及快照。</td></tr>'}</tbody></table></section>
  ${selected?`<aside class="panel"><div class="panel-head"><h2>记录详情</h2>${badge(selected.archive?'服务端归档':selected.sample?'示例记录':'运行快照')}</div><div class="run-details"><dl><dt>项目</dt><dd>${esc(selected.projectName)}</dd><dt>运行标识</dt><dd class="mono">${esc(selected.id)}</dd><dt>仿真时间</dt><dd>${number(selected.time,1)} s</dd><dt>最后落盘</dt><dd>${esc(selected.archive?.persisted_at||'—')}</dd><dt>记录点数</dt><dd>${selected.history.length}${selected.archive?` / 共 ${selected.totalRows} 帧（抽稀间隔 ${selected.archiveStride}）`:''}</dd><dt>状态</dt><dd>${esc(selected.status)}</dd></dl><h3>参数快照</h3><div class="code-preview">${esc(JSON.stringify(selected.params,null,2))}</div>
  ${(selected.archive?.frame?.diagnostics||[]).length?`<div class="notice">${esc(selected.archive.frame.diagnostics.map(d=>d.message).join('；'))}</div>`:''}
  ${(selected.events||[]).slice(-5).map(e=>`<p>${number(e.t,1)} s · ${esc(e.text)}</p>`).join('')}<div class="stack" style="margin-top:18px">${btn('record-curves','查看该次曲线','Activity',`data-id="${selected.id}" ${selected.history.length?'':'disabled'}`,'primary')}${btn('export','导出记录 JSON','FileJson',`data-format="record" data-id="${selected.id}"`)}${selected.projectId?btn('open-project','打开来源项目','ArrowUpRight',`data-id="${selected.projectId}"`):''}</div></div></aside>`:''}</div></div>`;
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action="pid-example"]');
  if(!button)return;
  try {
    const response=await fetch('/api/v1/examples/'+button.dataset.kind,{headers:engine.authHeaders()});
    if(!response.ok)throw Error('无法读取控制示例');
    const model=await response.json(),bindings=engine.catalog.prototype_parameter_bindings;
    const nodes=model.instances.map((n,i)=>{
      const definition=model.modules.find(m=>m.id===n.module_id), params={};
      for(const [uiName,id] of Object.entries(bindings[n.module_id] || {})) {
        const spec=definition.parameters.find(p=>p.id===id), value=n.parameters[id] ?? spec.default;
        params[uiName]=spec.unit ? value/spec.unit.display_scale+spec.unit.display_offset : value;
      }
      return makeInstance(n.id,n.module_id,n.name,100+i*180,230,params);
    });
    const pg={id:'main',name:'控制回路',zoom:1,pan:[0,0],nodes,edges:model.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    const owner=makeProject(uid('project'),model.name,'内置 PID 验收示例',pg);
    owner.controllers=model.controllers;owner.solver.duration=button.dataset.kind==='level'?600:1200;owner.solver.dt=1;
    state.projects.push(owner);normalizeState();markDirty(owner);openProject(owner.id);
  }catch(error){msg(error.message,true);}
});
function pidOptions(p) {
  const measurements=[],targets=[];
  for(const node of p.pages.flatMap(pg=>pg.nodes)) {
    const module=moduleOf(node), definition=module.manifest || engine.catalog?.modules.find(m=>m.id===module.kind);
    if(!definition) continue;
    for(const v of definition.variables.filter(v=>v.source!=='parameter' && v.sampleable))
      measurements.push([`${node.id}.${v.id}`,`${node.name} · ${v.label}${v.unit?' ('+v.unit.canonical_unit+')':''}`]);
    for(const spec of definition.parameters.filter(v=>v.runtime && v.writable && v.value_type==='number'))
      targets.push([`${node.id}.${spec.id}`,`${node.name} · ${spec.label}${spec.unit?' ('+spec.unit.canonical_unit+')':''}`,spec]);
  }
  return {measurements,targets};
}
function pidPanel(p) {
  const {measurements,targets}=pidOptions(p), active=!!p.run.live;
  const fields=[['setpoint','设定值'],['kp','比例 Kp'],['ki','积分 Ki（每秒）'],['kd','微分 Kd（秒）'],['sample_s','采样周期（秒）'],['minimum','输出下限'],['maximum','输出上限'],['manual_output','手动输出']];
  return `<section class="panel" style="margin-bottom:20px"><div class="panel-head"><h2>PID 反馈控制</h2>${btn('pid-example','液位示例','Droplets','data-kind="level"','small')}${btn('pid-example','温控示例','Thermometer','data-kind="temperature"','small')}${btn('add-pid','添加控制器','Plus',active?'disabled':'','small')}</div><div class="panel-body stack"><p class="muted">选择反馈变量和执行参数。数值使用选项标注的单位；运行中可调整设定值及手自动模式。</p><div class="fields"><label class="field"><span>计算节奏</span><select data-live-mode ${active?'disabled':''}>${option('realtime','按真实时间运行',p.solver.executionMode || 'realtime')}${option('fast','快速计算',p.solver.executionMode || 'realtime')}</select></label><label class="field"><span>速度倍率</span><input data-live-speed type="number" min="0.1" max="100" value="${p.solver.speedRatio || 1}" ${active?'disabled':''}></label></div>${(p.controllers || []).map(c=>`<section class="panel" data-pid-card="${esc(c.id)}"><div class="panel-head"><strong>${esc(c.id)}</strong>${btn('remove-pid','移除','Trash2',`data-id="${esc(c.id)}" ${active?'disabled':''}`,'small')}</div><div class="panel-body fields"><label class="field"><span>反馈变量</span><select data-pid-id="${esc(c.id)}" data-pid-field="measurement" ${active?'disabled':''}>${measurements.map(([v,l])=>option(v,l,c.measurement)).join('')}</select></label><label class="field"><span>执行参数</span><select data-pid-id="${esc(c.id)}" data-pid-field="target" ${active?'disabled':''}>${targets.map(([v,l])=>option(v,l,c.instance_id+'.'+c.parameter_id)).join('')}</select></label><label class="field"><span>模式</span><select data-pid-id="${esc(c.id)}" data-pid-field="mode">${option('auto','自动',c.mode)}${option('manual','手动',c.mode)}</select></label>${fields.map(([key,label])=>`<label class="field"><span>${label}</span><input type="number" step="any" data-pid-id="${esc(c.id)}" data-pid-field="${key}" value="${c[key] ?? ''}" ${active && !['setpoint','manual_output'].includes(key)?'disabled':''}></label>`).join('')}</div><div class="panel-body" data-pid-readout="${esc(c.id)}">${pidReadout(p,c)}</div></section>`).join('') || '<p>尚未配置控制器；可先运行模型，再选择反馈变量。</p>'}</div></section>`;
}
function pidReadout(p,c) {
  const row=p.run.history.at(-1)?.canonical || {};
  return `测量 ${number(row['controller.'+c.id+'.measurement'],3)} · 输出 ${number(row['controller.'+c.id+'.output'],3)} · t = ${number(p.run.time,2)} s`;
}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action="add-pid"],[data-action="remove-pid"]');
  if(!button) return;
  const p=project(); if(p.run.live) return;
  p.controllers ||= [];
  if(button.dataset.action==='remove-pid') p.controllers=p.controllers.filter(c=>c.id!==button.dataset.id);
  else {
    const {measurements,targets}=pidOptions(p);
    if(!measurements.length || !targets.length) {msg('先添加有反馈变量和可调参数的设备。',true);return;}
    const target=targets.find(t=>!p.controllers.some(c=>c.instance_id+'.'+c.parameter_id===t[0]));
    if(!target) {msg('所有可调参数都已绑定控制器。',true);return;}
    const [instance_id,parameter_id]=target[0].split('.'),spec=target[2];
    p.controllers.push({id:'PID_'+Date.now(),measurement:measurements[0][0],instance_id,parameter_id,setpoint:0,kp:2,ki:0,kd:0,sample_s:.1,minimum:spec.minimum ?? -10000,maximum:spec.maximum ?? 10000,mode:'manual',manual_output:spec.default});
  }
  markDirty(p);render();
});
document.addEventListener('change',async event=>{
  const el=event.target,p=project();
  if(el.matches('[data-live-mode]')) {p.solver.executionMode=el.value;markDirty(p);return;}
  if(el.matches('[data-live-speed]')) {p.solver.speedRatio=numeric(el.value,.1,100);markDirty(p);return;}
  if(!el.dataset.pidField) return;
  const c=p.controllers.find(c=>c.id===el.dataset.pidId),key=el.dataset.pidField;
  if(!c) return;
  try {
    const value=['mode','measurement','target'].includes(key)?el.value:Number(el.value);
    if(p.run.live) await engine.confirmedCommand(p,{action:'controller',controller_id:c.id,parameter_id:key,value});
    if(key==='target') {
      [c.instance_id,c.parameter_id]=value.split('.');
      const spec=pidOptions(p).targets.find(t=>t[0]===value)[2];
      c.minimum=spec.minimum ?? -10000;c.maximum=spec.maximum ?? 10000;c.manual_output=spec.default;
    } else c[key]=value;
    markDirty(p);render();
  } catch(error) {msg(error.message,true);render();}
});
function controlLiveValues(p=project()){
  const values=p.run.history.at(-1)?.canonical||{}, keys=new Set((p.controlOutputs||'').split(/[\s,，]+/));
  return JSON.stringify(Object.fromEntries(Object.entries(values).filter(([key])=>keys.has(key)||key.startsWith(`script.${p.selectedControlId}.`))),null,2);
}
function renderControls(){const p=project(),programs=controls.normalize(p),selected=controls.current(p);return `<div class="page-shell">${heading('项目控制逻辑','按脚本组织控制策略；修改会在下次新运行生效。',btn('control-template','载入示例','FileCode2',selected?'':'disabled')+btn('preview-control','预览一个周期','StepForward',selected?'':'disabled','primary')+btn('save','保存脚本','Save'))}${pidPanel(p)}<section class="panel" style="margin-bottom:20px"><div class="panel-head"><h2>控制脚本</h2>${badge(programs.length+' / '+controls.MAX_PROGRAMS)}<span class="push"></span>${btn('add-control-program','新建脚本','Plus',programs.length>=controls.MAX_PROGRAMS?'disabled':'','small')}${btn('remove-control-program','删除所选脚本','Trash2',selected?`data-id="${esc(selected.id)}"`:'disabled','small')}</div><div class="panel-body">${programs.length?`<label class="field"><span>当前脚本</span><select data-control-program aria-label="选择控制脚本">${programs.map(program=>option(program.id,`${program.name} · ${program.id} · ${program.language!=='python'?'待迁移':program.enabled?'已启用':'未启用'}`,p.selectedControlId)).join('')}</select></label>`:'<p>尚无控制脚本。新建脚本后可编辑、预览并单独启用。</p>'}</div></section>${selected?`<details open><summary>编辑 ${esc(selected.id)}</summary><div class="connection-layout"><aside class="stack"><section class="panel"><div class="panel-head"><h3>控制程序</h3>${badge(p.controlLanguage==='python'?'Python':'旧脚本待迁移',p.controlLanguage==='python'?'good':'warn')}</div><div class="panel-body stack">
  <label class="check-label"><input type="checkbox" data-control-enabled ${p.controlEnabled?'checked':''} ${p.controlLanguage!=='python'?'disabled':''}>启用 Python 控制（下次新运行生效）</label>
  <label class="field"><span>脚本语言</span><select data-control-language aria-label="脚本语言">${option('python','Python',p.controlLanguage)}${p.controlLanguage!=='python'?option('legacy','旧脚本文本（待迁移）',p.controlLanguage):''}</select></label>
  <label class="field"><span>名称</span><input value="${esc(p.controlConfig.name)}" aria-label="控制程序名称" data-control-name></label><label class="field"><span>控制周期</span><div class="field-unit"><input type="number" value="${p.controlConfig.period}" min="1" max="60000" step="1" data-control-setting="period" aria-label="控制周期"><span>ms</span></div></label><label class="field"><span>执行超时</span><div class="field-unit"><input type="number" value="${p.controlTimeout}" min="0.1" max="30" step="0.1" data-control-timeout aria-label="控制执行超时"><span>s</span></div></label></div></section>
  <section class="panel"><div class="panel-head"><h3>输入与输出（引擎单位）</h3></div><div class="panel-body stack"><label class="field"><span>声明输入，一行一个</span><textarea data-control-inputs aria-label="控制输入">${esc(p.controlInputs)}</textarea></label><label class="field"><span>声明输出，一行一个</span><textarea data-control-outputs aria-label="控制输出">${esc(p.controlOutputs)}</textarea></label><small>例如 V1.mass_flow_kg_s、V1.param.opening_ratio；PID 设定值为 controller.ID.setpoint。开度 0–1，温度 K，压力 Pa。</small></div></section>
  <div class="notice">${icon('Info')}<span>${p.controlLanguage==='python'?'initialize(ctx) → step(ctx, dt_s) → finalize(ctx)。ctx.read / ctx.write 只访问声明的变量；ctx.state 保存脚本状态。预览真实执行一个周期，返回拟写入值；新建动态运行才会应用。':'已保留旧脚本文本。请手动迁移或载入 Python 示例，再选择 Python 并启用。'}</span></div></aside>
  <div class="panel"><div class="code-toolbar">${icon('FileCode2')}<span class="mono">${esc(p.id)} / ${esc(selected.id)}.${p.controlLanguage==='python'?'py':'txt'}</span><span class="push"></span>${badge(p.controlEnabled?'下次动态运行启用':'未启用')}</div><div class="code-editor" style="height:365px;min-height:300px"><div class="code-lines" aria-hidden="true">${p.control.split('\n').map((_,i)=>i+1).join('\n')}</div><textarea id="control-code" data-control-code spellcheck="false" aria-label="项目控制脚本" wrap="off">${esc(p.control)}</textarea></div><div class="code-output" id="control-output" role="status">${esc(ui.controlOutput)}</div><div class="panel-body"><h3>当前运行的控制值</h3><pre class="code-preview" id="control-live">${esc(controlLiveValues(p))}</pre></div></div></div></details>`:''}</div>`;}

function connectionVariableRows(){return projectVariables().filter(v=>(v.id+v.name+v.device).toLowerCase().includes(ui.connectionSearch.toLowerCase())).map(v=>`<tr><td><span class="mono">${v.id}</span><small>${esc(v.device)} · ${v.name}</small></td><td class="num mono">${number(v.value,3)}</td><td>${v.unit}</td><td>${badge(v.writable?'可设置':'只读',v.writable?'warn':'')}</td><td>${badge('示例','blue')}</td><td><div class="row gap-6">${ibtn('copy-var','复制变量标识','Copy',`data-value="${v.id}"`)}${ibtn('add-specific-curve','加入曲线','Activity',`data-id="${v.id}" data-label="${esc(v.device+' · '+v.name)}"`)}</div></td></tr>`).join('');}
function renderConnections(){return `<div class="page-shell">${heading('数据与外部对接','统一查找变量，配置接口、串口与消息观察。',badge('接口调用已接入 · 串口与绑定为演示','warn')+btn('save','保存对接配置','Save'))}<section class="panel"><nav class="tabs" aria-label="数据对接页面">${[['variables','变量浏览','Table2'],['api','接口调用','Braces'],['serial','串口配置','Plug'],['bindings','变量绑定','Cable'],['messages','消息中心','MessageSquare']].map(([k,v,i])=>`<button data-action="connection-tab" data-value="${k}" class="${ui.connectionTab===k?'active':''}">${icon(i)}${v}</button>`).join('')}</nav><div class="panel-body">${connectionContent()}</div></section></div>`;}
function connectionContent(){
  if(ui.connectionTab==='variables')return `<div class="filterbar"><label class="search">${icon('Search')}<input data-filter="connectionSearch" aria-label="搜索对接变量" placeholder="设备、变量名或标识" value="${esc(ui.connectionSearch)}"></label><span class="muted">${esc(project().name)}</span><span class="push"></span>${btn('export','导出变量表','Download','data-format="variables"','small')}</div><div class="table-wrap"><table><thead><tr><th>变量标识 / 名称</th><th class="num">当前值</th><th>单位</th><th>读写属性</th><th>数据来源</th><th></th></tr></thead><tbody id="connection-variable-rows">${connectionVariableRows()}</tbody></table></div>`;
  if(ui.connectionTab==='api')return `<div class="connection-layout"><aside class="stack"><h3>调用场景</h3><div class="side-nav">${[['read','读取变量','ArrowDownToLine'],['set','批量写入','Pencil'],['stream','订阅推送','Activity'],['status','运行状态','Info']].map(([k,l,i])=>`<button class="${(ui.apiKind||'read')===k?'active':''}" data-action="api-example" data-value="${k}">${icon(i)}${l}</button>`).join('')}</div><label class="field"><span>当前运行</span><input value="${esc(project().run.id||'尚未运行')}" readonly></label><div class="notice">${icon('Info')}<span>${engine.health?.auth?.required?'服务已开启令牌认证：外部调用需要 Authorization 头。':'服务只监听本机，未开启认证；对外开放前请用令牌启动（见 README）。'}</span></div></aside><div class="stack"><div class="row"><span class="badge blue">GET</span><strong class="mono" id="api-path"></strong><span class="push"></span>${btn('api-preview','发送请求','Play','','primary')}</div><div class="code-preview" id="api-request"></div><div class="code-output" id="api-response" role="status"></div></div></div>`;
  if(ui.connectionTab==='serial'){const c=state.connectors.find(c=>c.id===ui.selectedConnector&&c.kind==='serial')||state.connectors.find(c=>c.kind==='serial');return `<div class="connection-layout"><aside class="stack"><div class="row spread"><h3>串口连接</h3>${ibtn('add-connector','添加串口连接','Plus')}</div><div class="side-nav">${state.connectors.filter(c=>c.kind==='serial').map(c=>`<button data-action="select-connector" data-id="${c.id}" class="${c.id===ui.selectedConnector?'active':''}">${icon('Plug')}<span>${esc(c.name)}<small class="muted" style="display:block">${c.port} · ${c.baud}</small></span></button>`).join('')}</div><div class="notice">${icon('Info')}串口打开和收发仅模拟状态，不访问硬件。</div></aside><div class="stack"><div class="row spread"><div><h3>${esc(c.name)}</h3><small class="muted">保存后保留连接参数</small></div>${badge(c.connected?'演示已连接':'未连接',c.connected?'good':'')}</div><div class="fields"><label class="field"><span>端口</span><select data-connector-id="${c.id}" data-connector-field="port">${['COM1','COM3','COM5'].map(x=>option(x,x,c.port)).join('')}</select></label><label class="field"><span>波特率</span><select data-connector-id="${c.id}" data-connector-field="baud">${['9600','19200','57600','115200'].map(x=>option(x,x,c.baud)).join('')}</select></label><label class="field"><span>数据位</span><select data-connector-id="${c.id}" data-connector-field="bits">${option('8','8',c.bits||'8')}${option('7','7',c.bits||'8')}</select></label><label class="field"><span>校验位</span><select data-connector-id="${c.id}" data-connector-field="parity">${['None','Even','Odd'].map(x=>option(x,x,c.parity||'None')).join('')}</select></label></div><div class="row">${btn('connect-demo',c.connected?'断开演示':'连接演示','Plug',`data-id="${c.id}"`,'primary')}<small class="muted">${c.connected?'可以模拟一条消息收发':'尚未启动模拟连接'}</small></div><div class="spacer"></div><h3>发送消息</h3><div class="row"><input id="serial-message" aria-label="串口模拟发送消息" value="#Get/V1.OPENING" style="flex:1">${btn('serial-send','模拟发送','ArrowUpRight',`data-id="${c.id}" ${c.connected?'':'disabled'}`)}</div><div class="code-output" id="serial-output" role="status">等待模拟消息。</div></div></div>`;}
  if(ui.connectionTab==='bindings')return `<div class="stack"><div class="row spread"><div><h3>输入输出映射</h3><p class="muted" style="font-size:12px;margin-top:4px">给外部字段指定变量、方向与单位。</p></div>${btn('add-binding','添加映射','Plus','','primary')}</div><div class="table-wrap"><table><thead><tr><th>外部字段</th><th>项目变量</th><th>方向</th><th>单位</th><th>状态</th></tr></thead><tbody id="binding-rows">${bindingsForProject().map((b,i)=>`<tr><td class="mono">${esc(b.external)}</td><td><select data-binding-index="${i}" aria-label="映射 ${i+1} 的变量">${projectVariables().filter(v=>b.direction!=='write'||v.writable).map(v=>option(v.id,v.id+' · '+v.name,b.variable)).join('')}</select></td><td>${badge(b.direction==='write'?'外部 → 项目':'项目 → 外部',b.direction==='write'?'warn':'blue')}</td><td>${esc(b.unit)}</td><td>${badge('未连接')}</td></tr>`).join('')}</tbody></table></div><div class="notice">${icon('Info')}外部写入目标的类型、范围和单位需与变量定义一致；此处仅保存映射配置。</div></div>`;
  return `<div class="stack"><div class="row spread"><h3>消息与事件</h3><div class="row">${badge(state.messages.length+' 条记录')}${btn('demo-message','生成示例消息','Plus','','small')}${btn('export','导出消息','Download','data-format="messages"','small')}</div></div><div class="log-list" style="max-height:560px">${state.messages.map(m=>`<div class="log-line"><time>${esc(m.time)}</time><span class="log-kind">${esc(m.kind)}</span><span>${esc(m.text)}</span></div>`).join('')}</div></div>`;
}
function anchorOptions(p){return p.pages.flatMap(pg=>pg.nodes).flatMap(n=>moduleOf(n).ports.map(port=>[`${n.id}:${port.id}`,`${n.id} ${n.name} · ${port.label||port.id}`]));}
function circuitFluidsMarkup(p){
  const rows=p.circuitFluids||[],anchors=anchorOptions(p),circuits=engine.circuits?.(p.id)||[];
  return `<div class="settings-section"><div class="row spread"><h3>回路工质</h3>${btn('add-circuit-fluid','添加回路工质','Plus','','small')}</div><p class="muted">端口经连接和设备内部通路连成一个回路（关闭的阀门不分隔回路，换热器两侧是两个回路）。选一个端口代表回路并指定工质，其余回路用上面的默认介质。</p>${rows.map((c,i)=>`<div class="fields" data-circuit-row="${i}"><label class="field"><span>回路端口</span><select data-circuit-field="anchor" data-index="${i}">${anchors.map(([v,l])=>option(v,l,c.anchor.instance_id+':'+c.anchor.port_id)).join('')}</select></label><label class="field"><span>预设介质</span><select data-circuit-field="medium" data-index="${i}">${MEDIA.map(([k,n])=>option(k,n,c.medium||'water')).join('')}</select></label><label class="field"><span>物性字符串（可选）</span><input data-circuit-field="fluid" data-index="${i}" value="${esc(c.fluid||'')}" placeholder="如 REFPROP::R134A" spellcheck="false"></label><label class="field"><span>比例基准</span><select data-circuit-field="fluidReference" data-index="${i}">${option('mass','质量分数',c.fluidReference||'mass')}${option('mole','摩尔分数',c.fluidReference||'mass')}</select></label>${btn('remove-circuit-fluid','移除','Trash2',`data-index="${i}"`,'small')}</div>`).join('')||'<p>所有回路使用默认介质。</p>'}${circuits.length>1?`<div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>回路</th><th>工质</th><th>来源</th><th>端口数</th></tr></thead><tbody>${circuits.map(c=>`<tr><td><span class="series-key" style="background:${CIRCUIT_COLORS[c.id%CIRCUIT_COLORS.length]}"></span> ${c.id+1}</td><td>${esc(c.fluid.fluid)}</td><td>${esc(c.source==='project'?'项目默认':c.source)}</td><td>${c.ports.length}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted" style="font-size:12px">点击画布上的“检查连接”后显示各回路及其工质。</p>'}</div>`;
}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action="add-circuit-fluid"],[data-action="remove-circuit-fluid"]');
  if(!button) return;
  const p=project();p.circuitFluids ||= [];
  if(button.dataset.action==='remove-circuit-fluid') p.circuitFluids.splice(Number(button.dataset.index),1);
  else {
    const anchors=anchorOptions(p);if(!anchors.length){msg('先在画布上放置设备。',true);return;}
    const [instance_id,port_id]=anchors[0][0].split(':');
    p.circuitFluids.push({id:'circuit_'+Date.now(),anchor:{instance_id,port_id},medium:'meg30',fluid:'',fluidReference:'mass'});
  }
  markDirty(p);render();
});
document.addEventListener('change',event=>{
  const el=event.target;if(!el.dataset.circuitField) return;
  const p=project(),row=p.circuitFluids?.[Number(el.dataset.index)];if(!row) return;
  if(el.dataset.circuitField==='anchor'){const [instance_id,port_id]=el.value.split(':');row.anchor={instance_id,port_id};}
  else row[el.dataset.circuitField]=el.value.trim();
  markDirty(p);
});
function renderSettings(){return `<div class="page-shell">${heading('项目与工作台设置','配置项目、介质、求解参数与界面偏好。',btn('save','保存设置','Save','','primary'))}<div class="settings-layout"><aside class="side-nav">${[['project','项目属性','Folder'],['medium','介质与单位','Droplets'],['solver','运行与求解','SlidersHorizontal'],['appearance','界面与布局','Monitor'],['storage','保存与交换','Database']].map(([k,l,i])=>`<button data-action="settings-tab" data-value="${k}" class="${ui.settingsTab===k?'active':''}">${icon(i)}${l}</button>`).join('')}</aside><section class="panel">${settingsContent()}</section></div></div>`;}
function settingsContent(){const p=project();
  if(ui.settingsTab==='project')return `<div class="settings-section"><h3>项目属性</h3><p>名称和说明用于项目列表、运行记录与导出文件。</p><div class="fields"><label class="field"><span>项目名称</span><input data-project-field="name" value="${esc(p.name)}" maxlength="50" aria-label="项目名称"></label><label class="field"><span>项目标识</span><input value="${p.id}" readonly></label><label class="field wide"><span>项目说明</span><textarea data-project-field="description" aria-label="项目说明" maxlength="240">${esc(p.description)}</textarea></label></div></div><div class="settings-section"><div class="row spread"><h3>画布</h3>${btn('new-canvas','添加画布','Plus','','small')}</div>${p.pages.map(pg=>`<div class="list-row" style="padding:12px 0">${icon('Layers')}<div class="grow"><strong>${esc(pg.name)}</strong><small>${pg.nodes.length} 个设备 · ${pg.edges.length} 条连接</small></div>${btn('rename-canvas','重命名','Pencil',`data-id="${pg.id}"`,'small ghost')}</div>`).join('')}</div>`;
  if(ui.settingsTab==='medium')return `<div class="settings-section"><h3>介质配置</h3><p>默认介质用于没有单独指定工质的回路；温度和压力范围由计算服务按各回路的流体检查。</p><div class="fields"><label class="field"><span>默认介质</span><select data-project-field="medium">${MEDIA.map(([key,name])=>option(key,name,p.medium)).join('')}</select></label><label class="field wide"><span>物性字符串（可选，填写后替代默认介质）</span><input data-project-field="fluid" value="${esc(p.fluid||'')}" placeholder="如 REFPROP::R407C.MIX、REFPROP::R32[0.5]&amp;R125[0.5]、HEOS::R134a" aria-label="物性字符串" spellcheck="false"></label><label class="field"><span>组分比例基准</span><select data-project-field="fluidReference">${option('mass','质量分数',p.fluidReference||'mass')}${option('mole','摩尔分数',p.fluidReference||'mass')}</select></label><label class="field"><span>显示单位方案</span><input value="工程单位 · 本轮原型" readonly></label></div>${circuitFluidsMarkup(p)}<p class="muted" style="font-size:12px">${(()=>{const r=engine.health?.capabilities?.refprop;if(!r?.installed)return '未检测到 REFPROP；可将内置副本放到 vendor/refprop9.1/，或设置 FLUIDNET_REFPROP_PATH，或安装到 Windows 默认安装目录。';const src={bundled:'内置',env:'环境变量',system:'系统安装'}[r.source]||'未知来源';return `已检测到 REFPROP${r.version?' '+esc(r.version):''}（${esc(src)}），可使用 REFPROP:: 前缀（纯质写名称，混合物写 A[x]&amp;B[y] 或预定义的 名称.MIX）。`})()}</p><div class="notice" style="margin-top:20px">${icon('Droplets')}换热器两侧回路保留独立的介质归属，不通过图形分组自动合并。</div></div><div class="settings-section"><h3>物理量与单位</h3><div class="table-wrap"><table><thead><tr><th>物理量</th><th>工程显示</th><th>内部约定</th></tr></thead><tbody>${[['绝对压力','kPa / MPa','Pa'],['温度','°C','K'],['质量流量','kg/s','kg/s'],['比焓','kJ/kg','J/kg'],['密度','kg/m³','kg/m³'],['比容','m³/kg','m³/kg']].map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="muted" style="margin:12px 0 0;font-size:12px">密度与比容是不同物理量，独立命名与换算。</p></div>`;
  if(ui.settingsTab==='solver')return `<div class="settings-section"><h3>运行设置</h3><p>设置仿真时间、时间步长及停止条件。原型记录配置并演示控制流程。</p><div class="fields"><label class="field"><span>运行模式</span><select data-solver-field="mode">${option('dynamic','动态',p.solver.mode)}${option('steady','稳态',p.solver.mode)}</select></label><label class="field"><span>仿真时长</span><div class="field-unit"><input type="number" data-solver-field="duration" value="${p.solver.duration}" min="1" max="86400" ${p.solver.continuous?'disabled':''}><span>s</span></div></label><label class="check-label"><input type="checkbox" data-solver-continuous ${p.solver.continuous?'checked':''}>持续运行（不设时长，直到停止；浏览器保留最近 2001 帧，曲线页可看全程抽稀）</label><label class="field"><span>时间步长</span><div class="field-unit"><input type="number" data-solver-field="dt" value="${p.solver.dt}" min=".01" max="60" step=".01"><span>s</span></div></label><label class="field"><span>最大迭代次数</span><input type="number" data-solver-field="maxIter" value="${p.solver.maxIter}" min="5" max="500"></label><label class="field"><span>水力算法</span><select data-solver-field="hydraulicMethod">${option('auto','自动（按未知量与稀疏度）',p.solver.hydraulicMethod||'auto')}${option('dense','稠密',p.solver.hydraulicMethod)}${option('sparse','稀疏',p.solver.hydraulicMethod)}</select></label></div></div><div class="settings-section"><h3>收敛判据</h3><p>质量与压力使用独立容差；数值设置需要在真实求解阶段验证。</p><div class="fields"><label class="field"><span>质量绝对容差</span><div class="field-unit"><input type="number" data-solver-field="massAtol" step="any" value="${p.solver.massAtol}" min="0"><span>kg/s</span></div></label><label class="field"><span>压力绝对容差</span><div class="field-unit"><input type="number" data-solver-field="pressureAtol" step="any" value="${p.solver.pressureAtol}" min="0"><span>Pa</span></div></label></div></div>`;
  if(ui.settingsTab==='appearance')return `<div class="settings-section"><h3>界面显示</h3><p>切换主题与画布辅助显示，原型会记住偏好。</p><div class="fields"><label class="field"><span>主题</span><select data-theme-select>${option('light','浅色',ui.theme)}${option('dark','深色',ui.theme)}</select></label><label class="field"><span>模块数值显示精度</span><select data-module-field="precision">${[2,4,6,8].map(n=>option(n,n+' 位小数',mod().precision)).join('')}</select></label></div><div style="margin-top:20px"><label class="check-label"><input type="checkbox" data-ui-toggle="pageGrid" ${ui.pageGrid?'checked':''}>显示画布点阵</label></div></div><div class="settings-section"><h3>窗口布局</h3><p>参数窗口可以移动、调整大小、置顶和收起。关闭查看窗口不会终止运行。</p>${btn('reset-windows','恢复窗口位置','Columns2')}${btn('nav','到画布查看','ArrowRight','data-route="workbench"','ghost')}</div><div class="settings-section"><h3>键盘操作</h3><div class="shortcut-grid" style="margin-top:15px">${shortcutMarkup()}</div></div>`;
  return `<div class="settings-section"><h3>原型保存</h3><p>保存当前浏览器中的项目、模块、型号、参数和配置。</p><div class="notice good">${icon('Database')}<span>${state.savedAt?'已保存原型草稿；再次保存会更新这份浏览器记录。':'当前使用内置示例，点击保存后记录你的编辑。'}</span></div><div class="row wrap" style="margin-top:18px">${btn('save','保存原型','Save','','primary')}${btn('export','导出原型 JSON','Download','data-format="prototype"')}${btn('import','导入原型 JSON','Upload')}</div></div><div class="settings-section"><h3>数据交换</h3><p>原型交换文件仅用于此设计版本，不直接修改正式项目工作区。</p><div class="row wrap">${btn('export','导出型号库','Database','data-format="models"')}${btn('export','导出变量表','Table2','data-format="variables"')}</div></div><div class="settings-section"><h3>恢复示例</h3><p>开始一轮新的原型体验前，可以先导出当前数据，再恢复示例。</p>${btn('reset-prototype','恢复内置示例','RotateCcw','','danger')}</div>`;
}
function shortcutMarkup(){return [['保存原型','Ctrl S'],['页面导航','Ctrl K'],['撤销 / 重做','Ctrl Z / Y'],['复制 / 粘贴设备','Ctrl C / V'],['删除选中对象','Delete'],['取消连线 / 关闭弹窗','Esc']].map(([label,key])=>`<div><span>${label}</span><kbd>${key}</kbd></div>`).join('');}
function renderHelp(){return `<div class="page-shell">${heading('页面导览与使用指南','先用已有设备完成一次调参，再按需进入自定义模块开发。',btn('page-map','页面导航','LayoutDashboard')+btn('start-modeling','从示例调参开始','ArrowRight','','primary')+btn('guided-demo','进入模块开发','Code2'))}<div class="journey">${[['01','打开示例','选择已有管网与设备'],['02','调整参数','编辑草稿，核对当前值'],['03','明确应用','确认变化与生效时刻'],['04','运行或单步','更新当前参数对应的结果'],['05','观察与保存','同屏对照曲线、保存记录']].map(([n,t,d])=>`<div class="journey-step"><span class="step-number">${n}</span><strong>${t}</strong><p>${d}</p></div>`).join('')}</div><div class="section-title"><h2>所有页面</h2><span class="muted">${Object.keys(PAGE_META).length} 个页面 · ${EDITOR_TABS.length} 个模块编辑页签</span></div><div class="help-grid">${Object.entries(PAGE_META).filter(([id])=>id!=='help').map(([id,[name,i,desc]])=>`<article class="help-card">${icon(i)}<h3>${name}</h3><p>${desc}</p>${btn('nav','打开页面','ArrowUpRight',`data-route="${id}"`,'small')}</article>`).join('')}</div><div class="fields" style="margin-top:22px"><section class="panel"><div class="panel-head"><h3>三个不同的对象</h3></div><div class="panel-body stack"><p><strong>模块定义</strong><br><span class="muted">描述图形、端口、变量、通路和算法。</span></p><p><strong>设备型号</strong><br><span class="muted">保存一组命名参数，并保留版本。</span></p><p><strong>项目实例</strong><br><span class="muted">放在项目中的设备，可单独改参数。</span></p></div></section><section class="panel"><div class="panel-head"><h3>保存、应用与运行</h3></div><div class="panel-body stack"><p><strong>保存</strong>：保留当前编辑草稿。</p><p><strong>应用</strong>：检查差异，将参数写入当前设备。</p><p><strong>运行</strong>：推进项目运行并记录结果。</p><div class="notice">${icon('Info')}项目通过后端求解；Python 模块包在独立 Worker 中执行。控制脚本仍为编辑预览。</div></div></section></div><section class="panel" style="margin-top:20px"><div class="panel-head"><h3>常用快捷键</h3></div><div class="panel-body shortcut-grid">${shortcutMarkup()}</div></section></div>`;}

// Device data is independent of the module's test values and other instances.
const sameValue = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const instanceWritable = v => v.writable && ['parameter', 'custom'].includes(v.origin);
const ownerOfInstance = n => state.projects.find(p => p.pages.some(pg => pg.nodes.includes(n))) || project();
function ensureInstanceVariables(n, m = moduleOf(n), owner = ownerOfInstance(n)) {
  n.variableState ||= { schema: 1, values: {}, draft: {}, banks: [{}, {}, {}], bankNames: clone(m.bankNames) };
  const data = n.variableState;
  for (const v of m.variables) {
    if (v.origin === 'custom') {
      if (!(v.id in data.values)) data.values[v.id] = clone(m.values[v.id] ?? v.value);
      if (!(v.id in data.draft)) data.draft[v.id] = clone(data.values[v.id]);
    }
    data.banks.forEach((bank, i) => {
      if (!(v.id in bank)) bank[v.id] = v.origin === 'port' ? null
        : v.origin === 'parameter' ? (i === 0 ? n.params[v.param] : m.banks[i][v.id] ?? n.params[v.param])
        : v.id === 'system:step' ? owner.solver.dt * 1000
        : v.id === 'system:run' ? 0
        : v.id === 'system:form' ? [125, 0, 0, 0, 0, 0, 0, 0]
        : v.id === 'system:mix' ? [1, 0, 0, 0, 0, 0, 0, 0] : clone(m.banks[i][v.id] ?? v.value);
    });
  }
  return data;
}
function instanceVariableValue(n, v, owner = ownerOfInstance(n)) {
  if (v.origin === 'parameter') return n.params[v.param];
  if (v.origin === 'custom') return ensureInstanceVariables(n).values[v.id];
  if (v.origin === 'runtime') return panelRow(owner.run)?.variableValues?.[n.id + ':' + v.id] ?? null;
  if (v.id === 'system:step') return owner.solver.dt * 1000;
  if (v.id === 'system:run') return owner.run.status === 'running' ? 1 : 0;
  if (v.id === 'system:form') return [125, 0, 0, 0, 0, 0, 0, 0];
  if (v.id === 'system:mix') return [1, 0, 0, 0, 0, 0, 0, 0];
  return v.origin === 'port' ? engine?.portValue(n, v, panelRow(owner.run)) ?? null : null;
}

function instanceDraftValue(n, v) {
  return v.origin === 'parameter' ? n.draft[v.param] : ensureInstanceVariables(n).draft[v.id];
}
function instanceCustomPending(n) {
  const data = ensureInstanceVariables(n);
  return moduleOf(n).variables.filter(v => v.origin === 'custom' && instanceWritable(v) && !sameValue(data.values[v.id], data.draft[v.id])).length;
}
function instanceEdits(n, bank = -1) {
  const data = ensureInstanceVariables(n);
  return Object.fromEntries(moduleOf(n).variables.filter(instanceWritable).map(v => [v.id, clone(bank < 0 ? instanceDraftValue(n, v) : data.banks[bank][v.id])]));
}
function validateInstanceEdits(n, values, m = moduleOf(n)) {
  for (const v of m.variables.filter(instanceWritable)) {
    const value = values[v.id], array = v.type.endsWith('[8]');
    if (array && (!Array.isArray(value) || value.length !== 8)) throw Error(`${v.label}必须包含 8 项。`);
    try {
      for (const item of array ? value : [value]) numeric(item, -1e12, 1e12, v.type.startsWith('int'));
      const def = (m.manifest ? manifestFields(m.manifest) : PARAM_DEFS[m.kind] || []).find(f => f[0] === v.param);
      if (def) numeric(value, def[3], def[4]);
    } catch (error) { throw Error(`${v.label}：${error.message}`); }
  }
}
function commitInstanceEdits(n, values) {
  const data = ensureInstanceVariables(n);
  for (const v of moduleOf(n).variables.filter(instanceWritable)) {
    if (v.origin === 'parameter') n.params[v.param] = n.draft[v.param] = values[v.id];
    else { data.values[v.id] = clone(values[v.id]); data.draft[v.id] = clone(values[v.id]); }
  }
  // Boolean/text/curve parameters have no projected variable row, so commit every declared draft.
  for (const spec of deviceParamSpecs(n)) if (spec.id in n.draft) n.params[spec.id] = clone(n.draft[spec.id]);
}
function instanceBankDiff(n, bank) {
  const data = ensureInstanceVariables(n);
  return moduleOf(n).variables.filter(v => instanceWritable(v) && !sameValue(instanceVariableValue(n, v), data.banks[bank][v.id]));
}
function applyInstanceBank(n, bank) {
  const values = instanceEdits(n, bank), differences = instanceBankDiff(n, bank);
  validateInstanceEdits(n, values);
  const owner = ownerOfInstance(n);
  openDialog(`库值 ${bank + 1} → ${n.id} · ${n.name}`, `仅应用可编辑参数与自定义变量，端口结果和项目系统设置保持只读。${pendingCount(n) ? '确认后会替换这台设备已有的待应用草稿。' : ''}`,
    diffMarkup(differences.map(v => [`${v.label} · ${v.unit}`, instanceVariableValue(n, v), values[v.id]])), () => {
      validateInstanceEdits(n, values); remember(); commitInstanceEdits(n, values);
      n.draftModelId = null; n.draftModelVersion = null;
      owner.run.events.push({ t: owner.run.time, kind: 'parameters', text: `${n.id} 应用库值 ${bank + 1}：${differences.map(v => `${v.name}=${values[v.id]}`).join('，')}` });
      markDirty(owner); render(); msg(`${n.id} 的库值 ${bank + 1} 已应用`);
    }, '确认应用', true);
}
function captureInstanceBank(n, bank) {
  const data = ensureInstanceVariables(n);
  confirmChange(`当前值 → ${n.id} 库值 ${bank + 1}`, '保存这台设备已生效的参数和当前结果。未应用草稿不会被存入；未采样的端口值保留为空。', () => {
    data.banks[bank] = Object.fromEntries(moduleOf(n).variables.map(v => [v.id, clone(instanceVariableValue(n, v))]));
    markDirty(ownerOfInstance(n)); renderFloats(); msg(`${n.id} 当前值已存入库值 ${bank + 1}`);
  }, '存入此库');
}
function variableWindowState(f) {
  return f.variables ||= { source: -1, search: '', group: 'all', onlyDiff: false, allBanks: false };
}
function variableDisplay(value, v, precision) {
  if (value === null || value === undefined) return '—';
  if (value === '') return '未填写';
  return Array.isArray(value) ? value.map(n => number(n, v.type.startsWith('int') ? 0 : 3)).join(', ') : number(value, v.type === 'int' ? 0 : precision);
}
function instanceValueCell(n, v, source, editable, value) {
  const m = moduleOf(n), text = variableDisplay(value, v, m.precision);
  const label = `${n.id} ${v.name} ${source < 0 ? '待应用' : '库值' + (source + 1)}`;
  const attrs = `data-id="${n.id}" data-instance-value="${esc(v.id)}" data-instance-source="${source}" aria-label="${esc(label)}"`;
  if (editable && v.type.endsWith('[8]')) return `<button type="button" class="instance-array" data-action="instance-array" ${attrs} title="${esc(text)}">${esc(text)} ${icon('Pencil')}</button>`;
  if (editable) {
    const def = paramDefs(n).find(f => f[0] === v.param);
    return `<input type="number" step="${v.type === 'int' ? '1' : 'any'}" ${def ? `min="${def[3]}" max="${def[4]}"` : ''} ${attrs} value="${esc(value)}">`;
  }
  return `<span class="instance-readonly" title="${esc(Array.isArray(value) ? value.join(', ') : value ?? '未采样')}">${esc(text)}</span>`;
}
function instanceVariableRows(f, n) {
  const m = moduleOf(n), data = ensureInstanceVariables(n), config = variableWindowState(f);
  const columns = config.allBanks ? [-1, 0, 1, 2] : [config.source];
  const groups = [
    ['parameter', '设备参数', m.variables.filter(v => v.origin === 'parameter')],
    ...m.ports.map(p => [p.id, `${p.label} · ${p.name} / ${DOMAINS[p.domain].label}`, m.variables.filter(v => v.port === p.id)]),
    ['custom', '自定义变量', m.variables.filter(v => v.origin === 'custom')],
    ['system', '系统变量 · 项目设置', m.variables.filter(v => v.origin === 'system')]
  ];
  let count = 0;
  const rows = groups.map(([group, title, variables]) => {
    const shown = variables.filter(v => {
      if (config.group !== 'all' && config.group !== v.origin) return false;
      if (!(n.id + ' ' + v.name + ' ' + v.label + ' ' + v.note).toLowerCase().includes(config.search.toLowerCase())) return false;
      if (!config.onlyDiff) return true;
      return instanceWritable(v) && columns.some(c => !sameValue(instanceVariableValue(n, v), c < 0 ? instanceDraftValue(n, v) : data.banks[c][v.id]));
    });
    if (!shown.length) return '';
    count += shown.length;
    return `<tr class="instance-group"><th colspan="${5 + columns.length}" scope="rowgroup">${esc(title)}<span>${shown.length}</span></th></tr>` + shown.map(v => {
      const current = instanceVariableValue(n, v);
      return `<tr data-instance-row="${esc(v.id)}"><th scope="row" title="${esc(n.id + '.' + v.name)}${instanceWritable(v) ? '' : ' · 只读'}"><span class="mono">${esc(n.id + '.' + v.name)}</span><small class="docked-variable-label" title="${esc(v.label + ' · ' + v.unit)}">${esc(v.label)} · ${esc(v.unit)}</small></th><td class="instance-variable-name" title="${esc(v.label)}">${esc(v.label)}</td><td class="instance-unit">${esc(v.unit)}</td><td class="num" data-instance-live="${esc(v.id)}">${instanceValueCell(n, v, -1, false, current)}</td>${columns.map(c => {
        const value = c < 0 ? (instanceWritable(v) ? instanceDraftValue(n, v) : null) : data.banks[c][v.id];
        const changed = instanceWritable(v) && !sameValue(current, value);
        return `<td class="num${changed ? ' edited' : ''}" data-instance-cell="${c}">${c < 0 && !instanceWritable(v) ? '<span class="muted">只读</span>' : instanceValueCell(n, v, c, c === config.source && instanceWritable(v), value)}</td>`;
      }).join('')}<td class="variable-actions">${variableObservationButton(n, v)}${ibtn('device-definition', `查看 ${v.name} 的变量定义`, 'ArrowUpRight', `data-id="${n.id}" data-variable="${esc(v.id)}"`)}</td></tr>`;
    }).join('');
  }).join('');
  return `<table class="instance-value-table"><thead><tr><th>变量标识</th><th>中文名称</th><th>单位</th><th class="num">当前值</th>${columns.map(c => `<th class="num${c === config.source ? ' editing-column' : ''}">${c < 0 ? '待应用草稿' : '库值 ' + (c + 1)}${c === config.source ? '<small>编辑此列</small>' : ''}</th>`).join('')}<th class="variable-actions">观察 / 定义</th></tr></thead><tbody>${rows || `<tr><td colspan="${5 + columns.length}" class="instance-empty">没有符合条件的变量</td></tr>`}</tbody></table><span class="instance-row-count">显示 ${count} / ${m.variables.length} 个变量</span>`;
}
function instanceVariablesBody(f, n) {
  const config = variableWindowState(f), data = ensureInstanceVariables(n), owner = ownerOfInstance(n);
  return `<div class="instance-variables">
    <div class="instance-source"><strong>${esc(n.id)} · ${esc(owner.name)}</strong><span data-instance-run>${statusText(owner.run)} · ${clockLabel(owner.run.time)}</span></div>
    <div class="instance-filters"><label class="search">${icon('Search')}<input data-instance-search="${n.id}" aria-label="${n.id} 搜索全部变量" value="${esc(config.search)}" placeholder="中文名称、变量标识"></label><select data-instance-group="${n.id}" aria-label="${n.id} 变量分组">${[['all', '全部分组'], ['parameter', '设备参数'], ['port', '端口变量'], ['custom', '自定义变量'], ['system', '系统变量']].map(([key, label]) => option(key, label, config.group)).join('')}</select><label class="instance-edit-source">编辑<select data-instance-source-select="${n.id}" aria-label="${n.id} 编辑目标">${option(-1, '待应用草稿', config.source)}${data.bankNames.map((name, i) => option(i, '库值 ' + (i + 1) + ' · ' + name, config.source)).join('')}</select></label></div>
    <div class="instance-bank-actions"><label class="check-label"><input type="checkbox" data-instance-toggle="allBanks" data-id="${n.id}" ${config.allBanks ? 'checked' : ''}>三组对照</label><label class="check-label"><input type="checkbox" data-instance-toggle="onlyDiff" data-id="${n.id}" ${config.onlyDiff ? 'checked' : ''}>仅可写差异</label>${config.source < 0 ? `<span>草稿 → ${esc(n.id)}</span><span class="badge ${pendingCount(n) ? 'warn' : 'good'}" data-pending-for="${n.id}">${pendingCount(n)} 项待应用</span>` : `<span>库值 ${config.source + 1} → ${esc(n.id)}</span><span class="badge warn" data-bank-diff>${instanceBankDiff(n, config.source).length} 项差异</span>${btn('capture-instance-bank', '当前值存入此库', 'Copy', `data-id="${n.id}" data-bank="${config.source}"`, 'small ghost')}`}</div>
    <div class="instance-table-wrap" data-instance-table="${n.id}">${instanceVariableRows(f, n)}</div>
    <div class="instance-footnote">${btn('save-instance-model', '保存为型号', 'Database', `data-id="${n.id}"`, 'small ghost')}<span>曲线记录已生效值。端口“—”表示未采样；保存保留草稿，确认应用后生效。</span></div>
  </div>`;
}
function editInstanceArray(n, id, source) {
  const v = moduleOf(n).variables.find(v => v.id === id);
  if (!v || !instanceWritable(v) || !v.type.endsWith('[8]')) return;
  const data = ensureInstanceVariables(n), value = source < 0 ? instanceDraftValue(n, v) : data.banks[source][id];
  openDialog(`${n.id} · ${v.label}`, source < 0 ? '编辑待应用草稿，确认应用后才改变当前值。' : `编辑这台设备的库值 ${source + 1}。`, `<div class="fields">${value.map((n, i) => field('item' + i, `[${i}]`, n, `type="number" step="${v.type.startsWith('int') ? '1' : 'any'}" required`)).join('')}</div>`, fields => {
    const result = value.map((_, i) => numeric(fields['item' + i], -1e12, 1e12, v.type.startsWith('int')));
    if (source < 0) data.draft[id] = result; else data.banks[source][id] = result;
    markDirty(ownerOfInstance(n)); renderFloats();
  }, '保存到草稿');
}
function updateInstanceVariableInput(el) {
  const n = instance(el.dataset.id), v = moduleOf(n).variables.find(v => v.id === el.dataset.instanceValue);
  if (!v || !instanceWritable(v) || v.type.endsWith('[8]')) return;
  const source = Number(el.dataset.instanceSource), data = ensureInstanceVariables(n), value = el.value === '' ? '' : Number(el.value);
  if (source < 0) { if (v.origin === 'parameter') n.draft[v.param] = value; else data.draft[v.id] = value; }
  else data.banks[source][v.id] = value;
  el.closest('td').classList.toggle('edited', !sameValue(instanceVariableValue(n, v), value));
  const shell = el.closest('.floater');
  const pending = shell.querySelector('[data-pending-for]'); if (pending) pending.textContent = `${pendingCount(n)} 项待应用`;
  const difference = shell.querySelector('[data-bank-diff]'); if (difference) difference.textContent = `${instanceBankDiff(n, source).length} 项差异`;
  const apply = shell.querySelector('[data-action="apply-instance"]'); if (apply) apply.disabled = !pendingCount(n);
  const bankApply = shell.querySelector('[data-action="apply-instance-bank"]'); if (bankApply) bankApply.disabled = !instanceBankDiff(n, source).length;
  markDirty(ownerOfInstance(n));
}
function refreshInstanceVariableReadouts(f, n) {
  const shell = root.querySelector(`[data-float-id="${f.id}"]`); if (!shell) return;
  const owner = ownerOfInstance(n), m = moduleOf(n);
  const runLabel = shell.querySelector('[data-instance-run]'); if (runLabel) runLabel.textContent = `${statusText(owner.run)} · ${clockLabel(owner.run.time)}`;
  for (const cell of shell.querySelectorAll('[data-instance-live]')) {
    const v = m.variables.find(v => v.id === cell.dataset.instanceLive);
    if (v) cell.innerHTML = instanceValueCell(n, v, -1, false, instanceVariableValue(n, v, owner));
  }
}
function validateInstanceVariableState(n, m) {
  const data = n.variableState; if (!data) return; // Older saved prototypes.
  const valueMap = value => value && typeof value === 'object' && !Array.isArray(value);
  if (data.schema !== 1 || !valueMap(data.values) || !valueMap(data.draft) || !Array.isArray(data.banks) || data.banks.length !== 3 || data.banks.some(bank => !valueMap(bank)) || !Array.isArray(data.bankNames) || data.bankNames.length !== 3 || data.bankNames.some(name => typeof name !== 'string')) throw Error('设备变量与三组库值数据不完整。');
  const validDraftNumber = x => x === '' || typeof x === 'number' && Number.isFinite(x);
  for (const v of m.variables) {
    const values = [...data.banks.map(b => b?.[v.id]), ...(v.origin === 'custom' ? [data.values[v.id], data.draft[v.id]] : [])];
    for (const value of values) {
      if (value === undefined || value === null && ['port','runtime'].includes(v.origin)) continue;
      if (v.type.endsWith('[8]') ? !Array.isArray(value) || value.length !== 8 || value.some(x => !validDraftNumber(x)) : !validDraftNumber(value)) throw Error(`${n.id} 的 ${v.name} 数据格式不合法。`);
    }
  }
}

// 建模工作区：布局偏好只影响查看方式，参数仍通过显式应用生效。
function currentProjectPending() {
  return project().pages.flatMap(p => p.nodes).reduce((sum, n) => sum + pendingCount(n), 0);
}

function fitNetwork(pg = activePage()) {
  if (!pg.nodes.length) { pg.viewBounds = [-35, -5, 1140, 510]; }
  else {
    const xs = pg.nodes.map(n => n.x), ys = pg.nodes.map(n => n.y);
    pg.viewBounds = [Math.min(...xs) - 65, Math.min(...ys) - 65,
      Math.max(240, Math.max(...xs) - Math.min(...xs) + 130),
      Math.max(240, Math.max(...ys) - Math.min(...ys) + 170)];
  }
  pg.zoom = 1; pg.pan = [0, 0];
}

function networkViewBox(pg) {
  const valid = Array.isArray(pg.viewBounds) && pg.viewBounds.length === 4 && pg.viewBounds.every(Number.isFinite) && pg.viewBounds[2] > 0 && pg.viewBounds[3] > 0;
  const [x, y, width, height] = valid ? pg.viewBounds : [-35, -5, 1140, 510], zoom = pg.zoom || 1;
  return `${x + (width - width / zoom) / 2 - pg.pan[0]} ${y + (height - height / zoom) / 2 - pg.pan[1]} ${width / zoom} ${height / zoom}`;
}

function projectParameterKey(owner = project()) {
  return JSON.stringify({scenarios:owner.scenarios||[],events:owner.events||[],activeScenarioId:owner.activeScenarioId||'',medium:owner.medium,fluid:owner.fluid,fluidReference:owner.fluidReference,fluidConfig:owner.fluidConfig,circuitFluids:owner.circuitFluids,thermalCouplings:owner.thermalCouplings,solverOptions:owner.solverOptions,controls:controls.key(owner), solver: owner.solver, modules: state.modules.filter(m => owner.pages.some(pg => pg.nodes.some(n => n.moduleId === m.id))).map(m => ({id:m.id,kind:m.kind,version:m.version,ports:m.ports,channels:m.channels})), pages: owner.pages.map(pg => ({
    nodes: pg.nodes.map(n => ({ id: n.id, moduleId: n.moduleId, params: n.params, values: n.variableState?.values })),
    edges: pg.edges,
  })) });
}

function workbenchResultState() {
  const run = project().run;
  if (run.history.length < 1) return { text: '尚未采样 · 运行或单步查看结果', tone: '' };
  if (!run.parameterKey) return { text: '已有结果 · 请单步核对当前参数', tone: 'warn' };
  if (run.parameterKey !== projectParameterKey()) return { text: '参数已变更 · 等待重新采样', tone: 'warn' };
  if (replayingKeyFrame(run)) return { text: `结果已更新 · ${clockLabel(run.history.at(-1).t)} · 回放：显示最近关键帧`, tone: 'good' };
  return { text: `结果已更新 · ${clockLabel(run.history.at(-1).t)}`, tone: 'good' };
}

function entryPathsMarkup() {
  return `<div class="entry-paths">
    <section class="entry-path primary-path"><span class="entry-icon">${icon('Network')}</span><div class="grow"><h2>先把系统跑起来</h2><p>打开泵阀示例，调整阀门，在同一屏观察支路流量。</p></div>${btn('start-modeling', '打开示例调参', 'ArrowRight', '', 'primary')}</section>
    <section class="entry-path"><span class="entry-icon">${icon('Code2')}</span><div class="grow"><h2>制作自己的模块</h2><p>配置端口、变量与代码，保存型号后用于项目。</p></div>${btn('guided-demo', '进入模块开发', 'ArrowRight')}</section>
  </div>`;
}

function startModeling() {
  let p = state.projects.find(p => p.id === 'water-net');
  if (!p) {
    if (state.projects.length >= 20) throw Error('项目数量已达上限，请从项目管理打开已有项目。');
    p = makeProject(uid('project'), '泵阀并联管网', '调参并观察两条支路的流量。', waterPage());
    state.projects.push(p); normalizeState(); markDirty(p);
  }
  ui.showChart = true; ui.showLibrary = false; ui.workbenchChart = 'flow'; ui.pinnedChart = null;
  openProject(p.id);
  const n = p.pages.flatMap(pg => pg.nodes).find(n => moduleOf(n).kind === 'valve');
  if (n) {
    p.activePage = p.pages.find(pg => pg.nodes.includes(n)).id;
    openDevice(n.id);
    const f = ui.floats.find(f => f.id === n.id);
    f.docked = innerWidth >= 1000; rememberWindow(f);
  }
  fitNetwork();
  saveUI(); render();
  msg('先运行或单步，再修改开度、应用参数，观察底部两条支路的曲线。');
}

function isDocked(f) {
  return !!f.docked && !f.minimized && innerWidth >= 1000;
}

function syncDockLayout() {
  const workbench = root.querySelector('.workbench');
  if (!workbench) return;
  const active = ui.floats.find(f => instance(f.id) && isDocked(f));
  workbench.classList.toggle('has-docked', !!active);
  workbench.classList.toggle('has-docked-variables', active?.tab === 'variables');
}

function dockWindowBounds(f) {
  const rect = document.getElementById('inspector-dock').getBoundingClientRect();
  return { x: rect.left, y: rect.top, w: rect.width, h: rect.height };
}

function toggleDeviceDock(id) {
  const f = ui.floats.find(f => f.id === id);
  if (!f) return;
  if (innerWidth < 1000 && !f.docked) { msg('较宽的窗口可将参数停靠到右侧；当前使用浮窗。'); return; }
  const next = !f.docked;
  for (const other of ui.floats) if (other.docked && other !== f) { other.docked = false; rememberWindow(other); }
  f.docked = next; f.minimized = false; delete f.restore;
  rememberWindow(f); markDirty(); renderFloats();
}

function chartDockChoices() {
  return [['flow', '主管与 A / B 支路流量'], ['pressure', '泵出口压力'], ['temperature', '泵出口温度']]
    .concat(state.charts.extra.filter(v => v.projectId === project().id).map(v => [v.id, v.label]));
}

function workbenchChartData() {
  const run = project().run;
  if (!chartDockChoices().some(([id]) => id === ui.workbenchChart)) ui.workbenchChart = 'flow';
  const key = ui.workbenchChart;
  if (key === 'flow') return { history: run.history, keys: ['q', 'a', 'b'] };
  if (key === 'pressure' || key === 'temperature') return { history: run.history, keys: [key] };
  const variable = state.charts.extra.find(v => v.projectId === project().id && v.id === key);
  const seriesKey = 'extra:' + key;
  SERIES[seriesKey] = { name: variable.label, unit: variable.unit, color: 'blue' };
  return { history: run.history.filter(r => extraVariableValue(r, variable) !== null).map(r => ({ t: r.t, [seriesKey]: extraVariableValue(r, variable) })), keys: [seriesKey] };
}

function parameterEvents() {
  return project().run.events.filter(e => e.kind === 'parameters' || /参数已应用|应用库值/.test(e.text));
}

function workbenchChartMarkup() {
  const { history, keys } = workbenchChartData();
  if (history.length < 2) return `<div class="dock-empty">${icon('Activity')}<strong>还没有可观察的曲线</strong><span>点击右侧“运行”或“单步”，这里将同步显示当前项目的示例结果。</span></div>`;
  return chartSvg(history, keys, 'workbench-flow-chart', false, { compact: true, events: parameterEvents() });
}

function workbenchChartReadout() {
  const { history, keys } = workbenchChartData(), last = history.at(-1);
  return history.length > 1 ? `${clockLabel(last.t)} · ` + keys.filter(k => state.charts.series[k] !== false).map(k => `${SERIES[k].short || SERIES[k].name} ${number(last[k], 3)} ${SERIES[k].unit}`).join(' · ') : '当前项目 · 等待采样';
}

function renderWorkbenchChart() {
  if (!ui.showChart) return '';
  workbenchChartData();
  const event = parameterEvents().at(-1);
  return `<section class="workbench-chart" aria-label="同屏曲线">
    <header class="dock-chart-head"><strong>${icon('Activity')} 同屏观察</strong><label class="sr-only" for="workbench-chart-source">同屏观察变量</label><select id="workbench-chart-source" data-workbench-chart>${chartDockChoices().map(([id, label]) => option(id, label, ui.workbenchChart)).join('')}</select><span class="dock-source" title="${esc(project().name)}">当前项目 · 后端水力结果</span><span class="push"></span>${ibtn('full-curves', '打开完整曲线页', 'Maximize2')}${ibtn('toggle-chart', '收起同屏曲线', 'X')}</header>
    <div class="dock-chart-meta"><span data-result-status></span><div class="chart-legend">${(ui.workbenchChart === 'flow' ? ['q', 'a', 'b'] : []).map(k => `<button data-action="toggle-series" data-value="${k}" aria-pressed="${state.charts.series[k] !== false}" class="${state.charts.series[k] === false ? 'off' : ''}"><span class="series-key ${SERIES[k].color}"></span>${SERIES[k].short}</button>`).join('')}</div></div>
    <div id="workbench-chart-plot">${workbenchChartMarkup()}</div>
    <div class="dock-readout"><span id="workbench-flow-chart-readout">${workbenchChartReadout()}</span>${btn('release-cursor', '恢复实时读数', 'RefreshCw', `${ui.pinnedChart === 'workbench-flow-chart' ? '' : 'hidden'}`, 'ghost small')}</div>
    <div class="dock-event" data-workbench-event title="${esc(event?.text || '')}">${event ? `${clockLabel(event.t)} · ${esc(event.text)}` : '点击曲线可固定读数；参数应用时刻会显示为竖向虚线。'}</div>
  </section>`;
}

function refreshWorkbenchChart() {
  const plot = document.getElementById('workbench-chart-plot');
  if (!plot) return;
  plot.innerHTML = workbenchChartMarkup();
  const readout = document.getElementById('workbench-flow-chart-readout');
  if (readout) readout.textContent = workbenchChartReadout();
  restoreChartCursor();
}

function syncWorkbenchStatus() {
  const result = workbenchResultState();
  root.querySelectorAll('[data-result-status]').forEach(el => { el.textContent = result.text; el.className = 'result-status ' + result.tone; });
  root.querySelectorAll('[data-float-save]').forEach(el => el.textContent = state.dirty ? '草稿未保存' : '草稿已保存');
  root.querySelectorAll('[data-float-keyframe]').forEach(el => { el.hidden = !replayingKeyFrame(project().run); });
  root.querySelectorAll('[data-device-apply-status]').forEach(el => {
    const n = instance(el.dataset.deviceApplyStatus);
    if (n) { const count = pendingCount(n); el.textContent = count ? `${count} 项待应用 · 保存不会使其生效` : '参数已生效'; el.className = count ? 'pending-note' : 'applied-note'; }
  });
}

// 重绘与实时采样后保留固定游标的仿真时间，不保留失效的屏幕坐标。
function paintChartCursor(id, requestedTime, pinned = false) {
  const svg = document.getElementById(id), data = chartRegistry.get(id);
  if (!svg || !data?.rows.length) return;
  const t = clamp(requestedTime, data.minT, data.maxT), x = data.left + (t - data.minT) / (data.maxT - data.minT) * (data.right - data.left);
  let i = data.rows.findIndex(r => r.t >= t); if (i < 0) i = data.rows.length - 1;
  const a = data.rows[Math.max(0, i - 1)], b = data.rows[i], fraction = b.t === a.t ? 0 : clamp((t - a.t) / (b.t - a.t), 0, 1);
  const value = k => Number(a[k] || 0) + (Number(b[k] || 0) - Number(a[k] || 0)) * fraction;
  const guide = svg.querySelector('[data-chart-guide]');
  if (guide) { guide.setAttribute('x1', x); guide.setAttribute('x2', x); guide.setAttribute('opacity', '1'); }
  for (const marker of svg.querySelectorAll('[data-hover-mark]')) { marker.setAttribute('cx', x); marker.setAttribute('cy', data.y(value(marker.dataset.hoverMark))); marker.setAttribute('opacity', '1'); }
  const readout = document.getElementById(id + '-readout');
  if (readout) readout.textContent = `${pinned ? '已固定 · ' : ''}${clockLabel(t)} · ` + data.keys.map(k => `${SERIES[k]?.name || k} ${number(value(k), 3)} ${SERIES[k]?.unit || ''}`).join(' · ');
}

function restoreChartCursor() {
  if (ui.pinnedChart && ui.chartCursor?.id === ui.pinnedChart) paintChartCursor(ui.pinnedChart, ui.chartCursor.time, true);
  root.querySelectorAll('[data-action="release-cursor"]').forEach(el => el.hidden = ui.pinnedChart !== 'workbench-flow-chart');
}

// 分组独立于模块保存，空分组也可恢复；旧存档从模块分类补齐分组。
const DEFAULT_MODULE_GROUPS = [...new Set(MODULE_SPECS.map(spec => spec[3]))];
const groupNameKey = name => name.normalize('NFC').toLocaleLowerCase();
function moduleGroupNames(data = state) {
  return [...new Set([...DEFAULT_MODULE_GROUPS, ...(data.moduleGroups || []),
    ...data.modules.map(m => m.category).filter(name => typeof name === 'string' && name.trim())])];
}

function checkGroupName(value, except = '') {
  const name = String(value || '').trim().normalize('NFC');
  if (!name) throw Error('请输入分组名称。');
  if (name.length > 32) throw Error('分组名称最多 32 个字符。');
  if (/[\u0000-\u001f\u007f]/.test(name)) throw Error('分组名称不能包含换行或控制字符。');
  if (name === '全部模块' || moduleGroupNames().some(group => group !== except && groupNameKey(group) === groupNameKey(name))) throw Error('此分组名称已存在，请换一个名称。');
  return name;
}

function collectModuleGroups(data) {
  const groups = moduleGroupNames(data).filter(name => !DEFAULT_MODULE_GROUPS.includes(name));
  if (groups.length > 64) throw Error('最多保留 64 个自建模块分组。');
  return groups;
}

function validateModuleGroups(data) {
  if (data.moduleGroups !== undefined && (!Array.isArray(data.moduleGroups) || data.moduleGroups.length > 64)) throw Error('模块分组列表不合法。');
  const names = data.moduleGroups || [];
  const validName = name => typeof name === 'string' && !!name.trim() && name === name.trim() && name.length <= 32 && !/[\u0000-\u001f\u007f]/.test(name) && name !== '全部模块';
  if (names.some(name => !validName(name) || DEFAULT_MODULE_GROUPS.includes(name)) || new Set(names.map(groupNameKey)).size !== names.length) throw Error('模块分组名称不合法或重复。');
  if (data.modules.some(m => m.category !== undefined && !validName(m.category))) throw Error('模块所属分组不合法。');
  collectModuleGroups(data);
}

function normalizeModuleGroups() {
  for (const m of state.modules) if (!m.category) m.category = '自定义模块';
  state.moduleGroups = collectModuleGroups(state);
  if (ui.category !== '全部模块' && !moduleGroupNames().includes(ui.category)) ui.category = '全部模块';
}

function moduleGroupDialog(previous = '') {
  if (previous && !state.moduleGroups.includes(previous)) throw Error('内置分类保留原名称。');
  openDialog(previous ? '重命名分组' : '新增分组', previous ? '组内模块会同步更新分类，项目设备与型号保持原引用。' : '创建一个空分组，随后可在组内新建模块或移入已有模块。',
    field('groupName', '分组名称', previous, 'required maxlength="32" placeholder="例如：冷却水系统"'), data => {
      const name = checkGroupName(data.groupName, previous);
      if (!previous && state.moduleGroups.length >= 64) throw Error('最多保留 64 个自建模块分组。');
      if (previous) {
        state.moduleGroups = state.moduleGroups.map(group => group === previous ? name : group);
        for (const m of state.modules) if (m.category === previous) m.category = name;
      } else state.moduleGroups.push(name);
      ui.category = name; ui.moduleSearch = ''; markDirty(); render();
      msg(previous ? '分组已重命名；保存原型后保留。' : '分组已创建，可新建模块或将已有模块移入。');
    }, previous ? '保存名称' : '创建分组');
}

function removeModuleGroup(name) {
  if (!state.moduleGroups.includes(name)) throw Error('内置分类不能删除。');
  if (state.modules.some(m => m.category === name)) throw Error('请先将组内模块移到其他分组，再删除空分组。');
  confirmChange('删除空分组', `删除“${name}”，现有模块、型号和项目设备保持原样。`, () => {
    if (state.modules.some(m => m.category === name)) throw Error('分组中仍有模块，请先调整所属分组。');
    state.moduleGroups = state.moduleGroups.filter(group => group !== name);
    ui.category = '全部模块'; markDirty(); render(); msg('空分组已删除。');
  }, '删除分组');
}

function moveModuleGroup(id) {
  const m = state.modules.find(m => m.id === id);
  if (!m) return;
  openDialog('调整模块分组', `${m.name} · 仅改变模块库中的归类。`,
    selectField('category', '所属分组', moduleGroupNames().map(name => [name, name]), m.category), data => {
      if (!moduleGroupNames().includes(data.category)) throw Error('请选择已有分组。');
      if (m.category !== data.category) { m.category = data.category; markDirty(); }
      ui.category = m.category; ui.moduleSearch = ''; render(); msg(`${m.name} 已归入“${m.category}”。`);
    }, '确认分组');
}

function moduleGroupSidebar() {
  const categories = ['全部模块', ...moduleGroupNames()];
  return `<aside class="side-nav module-group-nav" aria-label="模块分类">
    <div class="module-group-heading"><span>模块分类</span>${btn('new-module-group', '新增分组', 'Plus', '', 'ghost small')}</div>
    <div class="module-group-list">${categories.map(name => {
      const count = name === '全部模块' ? state.modules.length : state.modules.filter(m => m.category === name).length;
      return `<button data-action="module-category" data-value="${esc(name)}" class="${ui.category === name ? 'active' : ''}" aria-pressed="${ui.category === name}" title="${esc(name)}">${icon(name === '全部模块' ? 'Boxes' : 'Folder')}<span>${esc(name)}</span><small class="push muted">${count}</small></button>`;
    }).join('')}</div><div class="spacer"></div><div class="module-group-links"><button data-action="nav" data-route="nodes">${icon('Waypoints')}节点与端口定义</button><button data-action="page-map">${icon('LayoutDashboard')}页面导航</button></div>
  </aside>`;
}

const isReferenceModule = m => m.category === '倍思鹿参考模块';
function renderModules() {
  const groups = moduleGroupNames();
  if (ui.category !== '全部模块' && !groups.includes(ui.category)) ui.category = '全部模块';
  const members = state.modules.filter(m => ui.category === '全部模块' || m.category === ui.category);
  const list = members.filter(m => (m.name + m.code).toLowerCase().includes(ui.moduleSearch.toLowerCase()));
  const custom = state.moduleGroups.includes(ui.category), blankGroup = ui.category !== '全部模块' && !members.length;
  return `<div class="page-shell">${heading('模块库', '定义可复用的设备：图形、端口、通路、变量与算法。', btn('nav', '节点定义', 'Waypoints', 'data-route="nodes"') + btn('new-module', '新建模块', 'Plus', '', 'primary'))}
    <div class="split-view">${moduleGroupSidebar()}<div class="module-content">
      ${ui.category === '倍思鹿参考模块' ? `<div class="notice module-reference-note">${icon('Info')}<span>来自倍思鹿参考实现，L1/L2/L3 验证状态见文档。</span></div>` : ''}
      ${ui.category !== '全部模块' ? `<div class="module-group-context"><div class="grow"><h2>${esc(ui.category)}</h2><small>${custom ? '自建分组' : '内置分类'} · ${members.length} 个模块</small></div>${custom ? btn('rename-module-group', '重命名', 'Pencil', `data-value="${esc(ui.category)}"`, 'small') + btn('delete-module-group', '删除分组', 'Trash2', `data-value="${esc(ui.category)}" ${members.length ? 'disabled title="请先将组内模块移到其他分组"' : ''}`, 'small') : ''}</div>` : ''}
      <div class="filterbar"><label class="search">${icon('Search')}<input data-filter="moduleSearch" aria-label="搜索模块" placeholder="名称或模块标识" value="${esc(ui.moduleSearch)}"></label><span class="push muted">${list.length} 个模块</span><div class="segmented" role="group" aria-label="模块库视图">${[['cards', '卡片视图', 'Grid2X2'], ['list', '紧凑列表', 'List']].map(([value, label, glyph]) => `<button data-action="module-view" data-value="${value}" aria-label="${label}" title="${label}" aria-pressed="${ui.moduleView === value}" class="${ui.moduleView === value ? 'active' : ''}">${icon(glyph)}</button>`).join('')}</div>${btn('compile-preview', '批量检查预览', 'CheckCheck', '', 'small')}</div>
      <div id="module-results" class="module-grid${ui.moduleView === 'list' ? ' module-compact-list' : ''}">${list.map(m => `<article class="module-card" data-module-id="${m.id}"><div class="row module-card-title"><span class="object-icon">${icon(m.icon)}</span><div class="grow"><h3>${esc(m.name)}</h3><small class="muted mono">${esc(m.code)}</small></div>${isReferenceModule(m) ? badge('参考模块', 'good') : ''}${badge(m.runtime === 'python' ? (m.publishedManifest ? 'Python · v'+m.publishedManifest.version : 'Python · 未发布') + (m.dirty?' · 有草稿':'') : '内置 · v'+m.version,m.runtime === 'python' ? 'blue' : '')}</div><button class="module-group-chip" data-action="move-module-group" data-id="${m.id}" aria-label="调整 ${esc(m.name)} 的分组" title="调整所属分组">${icon('Folder')}<span>${esc(m.category)}</span>${icon('ChevronDown')}</button><p>${esc(m.description)}</p>${moduleEvidenceSummary(m)}<div class="stat-line"><span>${(m.parameters || PARAM_DEFS[m.kind] || []).length} 个参数</span><span>${m.ports.length} 个端口</span><span>${m.channels.length} 条通路</span><span>${m.variables.length} 个变量</span></div><div class="card-footer">${isReferenceModule(m) ? btn('module-doc', '说明', 'BookOpen', `data-id="${m.id}"`, 'small') : ''}${btn('edit-module', '编辑模块', 'Pencil', `data-id="${m.id}"`, 'small')}${m.runtime === 'python' ? btn('test-module','独立验证','CheckCheck',`data-id="${m.id}"`,'small') + btn('module-example','管网算例','Network',`data-id="${m.id}"`,'small') : ''}<span class="push"></span>${ibtn('insert-module', '插入项目 ' + m.name, 'Plus', `data-id="${m.id}"`)}</div></article>`).join('') || (blankGroup ? empty('分组已建好，添加第一个模块', '可在此分组中新建模块，也可从“全部模块”的模块卡片调整所属分组。', btn('new-module', '在此分组新建模块', 'Plus', '', 'primary')) : empty('没有匹配的模块', '尝试其他分类或关键词。'))}</div>
    </div></div></div>`;
}

function openModuleDoc(id) {
  const m = state.modules.find(item => item.id === id);
  if (!m) throw Error('模块不存在或已从目录中移除。');
  const manifest = m.manifest || {};
  const parameters = m.parameters || [], ports = manifest.ports || m.ports || [];
  const variables = manifest.variables || [], channels = manifest.channels || m.channels || [];
  const text = value => value && typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—');
  const parameterUnit = p => p.unit?.display_unit || p.unit?.canonical_unit || p.value_type || '—';
  const table = (heads, rows) => `<div class="table-wrap"><table><thead><tr>${heads.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const section = (title, note, heads, rows) => rows.length ? `<section class="module-doc-section"><h3>${esc(title)}<small>${esc(note)}</small></h3>${table(heads, rows)}</section>` : '';
  const body = `${section('参数', `${parameters.length} 项`, ['id', 'label', '默认值', '单位 / value_type'], parameters.map(p => [p.id, p.label || p.id, text(p.default), parameterUnit(p)]))}
    ${section('端口', `${ports.length} 个`, ['id', 'label', 'domain', 'direction'], ports.map(p => [p.id, p.label || p.id, p.domain || 'fluid', p.direction || '—']))}
    ${section('变量', `${variables.length} 个`, ['id', 'label', 'source', '单位'], variables.map(v => [v.id, v.label || v.id, v.source || '—', v.unit?.display_unit || v.unit?.canonical_unit || '—']))}
    ${section('通路', `${channels.length} 条`, ['id', 'relation', 'solver_model'], channels.map(c => [c.id, c.relation || c.kind || '—', c.solver_model || manifest.solver_model || '—']))}
    <p class="module-doc-hint">参考模块的映射/验证状态见仓库 docs/MODULE_KIT.md、docs/MAPPING_A.md、docs/MAPPING_C.md、docs/M2_L3_CALIBRATION.md。</p>`;
  openDialog(`${m.name} · v${m.version} · ${m.category}`, m.description || '参考模块说明', body, null, '', true);
}

// 画布操作与模块定义共用端口 / 通路，不根据图形猜测内部连接。
function deviceToolsMarkup(n) {
  if (!n) return '';
  return `<div class="device-tools" role="toolbar" aria-label="选中设备操作"><strong>${esc(n.id)} · ${esc(n.name)}</strong>${ibtn('open-device', '参数与型号', 'SlidersHorizontal', `data-id="${n.id}"`)}${ibtn('device-variables', '查看全部变量', 'Table2', `data-id="${n.id}"`)}${ibtn('choose-device-model', '选择设备型号', 'Database', `data-id="${n.id}"`)}${ibtn('rotate-device', '顺时针旋转 90° · R', 'RotateCw', `data-id="${n.id}"`)}${ibtn('rotate-device', '逆时针旋转 90° · Shift+R', 'RotateCcw', `data-id="${n.id}" data-direction="-1"`)}${ibtn('device-definition', '查看模块定义', 'Box', `data-id="${n.id}"`)}</div>`;
}
function syncDeviceSelection() {
  if (ui.route !== 'workbench') return;
  const n = activePage().nodes.find(n => n.id === ui.selectedNode);
  const props = document.getElementById('selected-properties'), tools = document.getElementById('canvas-device-tools');
  if (props) props.innerHTML = propertiesMarkup(n);
  if (tools) tools.innerHTML = deviceToolsMarkup(n);
  root.querySelectorAll('#network [data-node]').forEach(el => el.classList.toggle('selected', el.dataset.node === n?.id));
}
function rotateDevice(id, direction = 1) {
  const n = activePage().nodes.find(n => n.id === id); if (!n) return;
  remember(); n.rotation = ((n.rotation || 0) + direction * 90 + 360) % 360;
  ui.selectedNode = n.id; markDirty(project()); render();
  root.querySelector(`#network [data-node="${n.id}"]`)?.focus({ preventScroll: true });
}
function setDeviceTab(f, tab) {
  f.tab = tab;
  if (tab === 'variables' && !f.variablesOpened) {
    const r = page.getBoundingClientRect(); f.variablesOpened = true;
    f.w = Math.min(780, r.width - 16); f.h = Math.min(650, r.height - 16);
    f.x = r.right - f.w - 12; f.y = r.top + 12;
  }
}
function openDeviceVariables(id, variableId) {
  const n = instance(id); if (!n) return;
  openDevice(id);
  const f = ui.floats.find(f => f.id === id); setDeviceTab(f, 'variables');
  if (variableId) {
    const v = moduleOf(n).variables.find(v => v.id === variableId);
    if (v) Object.assign(variableWindowState(f), { search: v.name, group: 'all', onlyDiff: false, source: -1 });
  }
  renderFloats();
}
function chooseDeviceModel(id) {
  const n = instance(id); if (!n) return;
  const items = state.models.filter(item => item.moduleId === n.moduleId && !item.archived);
  if (!items.length) { openDevice(id); msg('此模块还没有型号，可从设备当前值或库值保存型号。'); return; }
  openDialog(`选择型号 · ${n.id}`, '所选型号进入设备草稿，预览并应用后生效。', selectField('model', '设备型号', items.map(item => [item.id, `${item.name} · v${item.version}`]), n.draftModelId || n.modelId || items[0].id), data => {
    stageModel(n, data.model); openDevice(id); setDeviceTab(ui.floats.find(f => f.id === id), 'parameters'); renderFloats();
    msg('型号已进入设备草稿。');
  }, '进入设备草稿');
}
function openDeviceDefinition(id, variableId) {
  const n = instance(id); if (!n) return;
  const origin = { projectId: project().id, pageId: activePage().id, nodeId: id, variableId };
  if (variableId) ui.variableSearch = moduleOf(n).variables.find(v => v.id === variableId)?.name || '';
  openEditor(n.moduleId, variableId ? 'attributes' : 'drawing', origin);
}
function returnToDevice() {
  const origin = ui.editorOrigin; if (!origin) return;
  const owner = state.projects.find(p => p.id === origin.projectId), pg = owner?.pages.find(pg => pg.id === origin.pageId);
  if (!pg?.nodes.some(n => n.id === origin.nodeId)) { ui.editorOrigin = null; navigate('modules'); return; }
  if (state.activeProject !== owner.id) openProject(owner.id);
  owner.activePage = pg.id; navigate('workbench');
  if (origin.variableId) openDeviceVariables(origin.nodeId, origin.variableId); else openDevice(origin.nodeId);
}
function deviceContextMarkup(id) {
  return `${btn('open-device', '参数与型号', 'SlidersHorizontal', `data-id="${id}"`)}${btn('device-variables', '全部变量', 'Table2', `data-id="${id}"`)}${btn('choose-device-model', '选择设备型号', 'Database', `data-id="${id}"`)}${btn('device-definition', '查看模块定义', 'Box', `data-id="${id}"`)}<div class="spacer"></div>${btn('rotate-device', '顺时针旋转 · R', 'RotateCw', `data-id="${id}"`)}${btn('rotate-device', '逆时针旋转 · Shift+R', 'RotateCcw', `data-id="${id}" data-direction="-1"`)}${btn('copy-device', '复制设备', 'Copy', `data-id="${id}"`)}${btn('delete-node', '删除设备', 'Trash2', `data-id="${id}"`)}`;
}
function internalChannels(n) {
  const m = moduleOf(n);
  return m.channels.filter(c => c.enabled && m.ports.some(p => p.id === c.input) && m.ports.some(p => p.id === c.output));
}
function internalChannelsMarkup(n) {
  const m = moduleOf(n);
  return `<g transform="rotate(${n.rotation || 0})" class="internal-channels" aria-hidden="true">${internalChannels(n).map(c => {
    const a = portOffset(n, m.ports.find(p => p.id === c.input)), b = portOffset(n, m.ports.find(p => p.id === c.output)), mid = (a.x + b.x) / 2;
    return `<path class="internal-channel" data-channel-id="${esc(c.id)}" data-channel-input="${esc(c.input)}" data-channel-output="${esc(c.output)}" d="M ${a.x} ${a.y} C ${mid} ${a.y}, ${mid} ${b.y}, ${b.x} ${b.y}"/>`;
  }).join('')}</g>`;
}
function showCanvasInspection(target) {
  const node = target?.closest?.('#network [data-node]'), port = target?.closest?.('[data-port-node]');
  ui.canvasInspection = node ? { id: node.dataset.node, portId: port?.dataset.portId } : null;
  paintCanvasInspection();
}
function paintCanvasInspection() {
  const hint = document.getElementById('canvas-inspection'); if (!hint) return;
  const selected = ui.canvasInspection, n = activePage().nodes.find(n => n.id === selected?.id), m = n && moduleOf(n), p = m?.ports.find(p => p.id === selected.portId);
  root.querySelectorAll('#network .inspecting,#network .channel-active').forEach(el => el.classList.remove('inspecting', 'channel-active'));
  hint.hidden = !n;
  if (!n) return;
  const node = root.querySelector(`#network [data-node="${n.id}"]`); node?.classList.add('inspecting');
  const channels = internalChannels(n).filter(c => !p || c.input === p.id || c.output === p.id);
  node?.querySelectorAll('[data-channel-id]').forEach(el => el.classList.toggle('channel-active', channels.some(c => c.id === el.dataset.channelId)));
  const edge = p && activePage().edges.find(e => e[1] === n.id && e[2] === p.id || e[3] === n.id && e[4] === p.id);
  const connected = edge ? `已连接 ${edge[1] === n.id ? edge[3] : edge[1]}` : '未连接';
  hint.textContent = p ? `${n.id} · ${p.label} (${p.name}) · ${DOMAINS[p.domain].label}${p.direction === 'in' ? '入口' : '出口'} · ${channels.map(c => c.name).join(' / ') || '未绑定内部通路'} · ${connected}` : `${n.id} · ${n.name} · ${channels.length ? channels.map(c => c.name).join(' / ') : '未设置内部通路'} · 双击参数，R 旋转`;
}

// 曲线绑定稳定的变量 ID，采样使用变量表中的单位；旧曲线仍可读取旧采样格式。
function variableObservation(n, v, owner = ownerOfInstance(n)) {
  if (v.type.endsWith('[8]')) return null;
  let legacyId = v.origin === 'parameter' ? n.id + '.' + v.param.toUpperCase() : null, factor = 1;
  if (v.origin === 'port') {
    if (!['FLOW', 'PRE', 'TEMP'].includes(v.id.split(':').at(-1))) return null;
    legacyId = null;
  } else if (!['parameter', 'custom', 'system', 'runtime'].includes(v.origin)) return null;
  return { id: n.id + '.' + v.name, legacyId, nodeId: n.id, variableId: v.id, identifier: n.id + '.' + v.name,
    name: v.label, device: n.name, unit: v.unit, value: instanceVariableValue(n, v, owner), writable: instanceWritable(v),
    origin: v.origin, sampleKey: n.id + ':' + v.id, legacyFactor: factor };
}
function projectVariables(owner = project()) {
  return owner.pages.flatMap(pg => pg.nodes).flatMap(n => moduleOf(n).variables.map(v => variableObservation(n, v, owner)).filter(Boolean));
}
function sampleVariableValues(owner, legacyValues) {
  return Object.fromEntries(projectVariables(owner).map(v => [v.sampleKey,
    v.origin === 'port'
      ? Number.isFinite(legacyValues[v.legacyId]) ? legacyValues[v.legacyId] * v.legacyFactor : null : clone(v.value)]));
}
function observeInstanceVariable(id, variableId) {
  const n = instance(id), v = n && moduleOf(n).variables.find(v => v.id === variableId), binding = v && variableObservation(n, v);
  if (!binding) throw Error('此变量暂不提供曲线采样；数组和未采样端口可在表格中查看。');
  const f = ui.floats.find(f => f.id === id);
  if (f) {
    if (innerWidth >= 1000) {
      for (const other of ui.floats) if (other !== f && other.docked) { other.docked = false; rememberWindow(other); }
      f.docked = true; f.minimized = false; rememberWindow(f);
    } else f.minimized = true;
  }
  addChartVariable(binding.id, undefined, true);
}
function variableObservationButton(n, v) {
  const binding = variableObservation(n, v), observed = binding && state.charts.extra.some(item => item.projectId === project().id && item.nodeId === n.id && item.variableId === v.id);
  const unavailable = v.type.endsWith('[8]') ? '数组暂不支持曲线' : '此端口变量尚未提供采样';
  return ibtn('observe-instance-variable', binding ? `同屏观察 ${n.id}.${v.name}` : unavailable, 'Activity', `data-id="${n.id}" data-variable="${esc(v.id)}" ${binding ? `aria-pressed="${!!observed}"` : 'disabled'}`);
}
function instanceModelValues(n, source) {
  const data = ensureInstanceVariables(n);
  if (!['current', 'draft', 'bank:0', 'bank:1', 'bank:2'].includes(source)) throw Error('请选择有效的数据来源。');
  return Object.fromEntries(moduleOf(n).variables.filter(instanceWritable).map(v => [v.id,
    clone(source === 'current' ? instanceVariableValue(n, v) : source === 'draft' ? instanceDraftValue(n, v) : data.banks[Number(source.slice(-1))][v.id]) ]));
}
function instanceModelPreview(n, source) {
  const values = instanceModelValues(n, source);
  return `<div class="table-wrap"><table class="model-source-table"><thead><tr><th>变量</th><th>保存值</th><th>单位</th></tr></thead><tbody>${moduleOf(n).variables.filter(instanceWritable).map(v => `<tr><td>${esc(v.label)}<small>${esc(v.name)}</small></td><td class="mono">${esc(variableDisplay(values[v.id], v, moduleOf(n).precision))}</td><td>${esc(v.unit)}</td></tr>`).join('')}</tbody></table></div>`;
}
function saveInstanceModel(id) {
  const n = instance(id); if (!n) return;
  const m = moduleOf(n), config = ui.floats.find(f => f.id === id), source = config?.tab === 'variables' && variableWindowState(config).source >= 0 ? 'bank:' + variableWindowState(config).source : 'current';
  const sources = [['current', '当前已生效值'], ['draft', '待应用草稿'], ...ensureInstanceVariables(n).bankNames.map((name, i) => ['bank:' + i, `库值 ${i + 1} · ${name}`])];
  if (!m.variables.some(instanceWritable)) throw Error('此模块没有可保存的设备参数或自定义变量。');
  openDialog(`保存设备型号 · ${n.id}`, '选择数据来源，将参数和自定义变量保存为可复用型号。端口结果与项目系统设置不写入型号。',
    `<div class="fields">${field('name', '型号名称', n.name + ' · 参数方案', 'required maxlength="60"')}<label class="field"><span>数据来源</span><select name="source" aria-label="型号数据来源" data-device-model-source="${n.id}">${sources.map(([key, label]) => option(key, label, source)).join('')}</select></label></div><div class="model-source-preview" id="device-model-preview">${instanceModelPreview(n, source)}</div>`, fields => {
      const name = fields.name.trim(), values = instanceModelValues(n, fields.source);
      if (!name) throw Error('请输入型号名称。');
      if (state.models.some(item => item.moduleId === m.id && item.name === name)) throw Error('同一模块已有此型号名称，请换一个名称。');
      if (state.models.length >= 500) throw Error('已达到型号数量上限。');
      validateInstanceEdits(n, values);
      const params = Object.fromEntries(m.variables.filter(v => v.origin === 'parameter').map(v => [v.param, values[v.id]]));
      const sourceLabel = `${n.id} · ${sources.find(([key]) => key === fields.source)[1]}`, note = `从 ${project().name} / ${sourceLabel} 保存`;
      state.models.push({ id: uid('model'), moduleId: m.id, name, description: note, sourceLabel, version: 1, moduleVersion: m.version,
        params, values: clone(values), bank: fields.source.startsWith('bank:') ? Number(fields.source.slice(-1)) + 1 : 1, archived: false,
        versions: [{ version: 1, note, params: clone(params), values: clone(values) }] });
      markDirty(); retainFocus(renderFloats); msg('型号已保存，可在当前设备或同模块设备中选择应用。');
    }, '保存型号', true);
}
function modelVariableSummary(item) {
  const variables = mod(item.moduleId).variables.filter(v => v.origin === 'custom' && item.values?.[v.id] !== undefined);
  return `${item.sourceLabel ? `<small class="muted">来源：${esc(item.sourceLabel)}</small>` : ''}${variables.length ? `<div class="model-variable-summary"><h3>自定义变量</h3><dl>${variables.map(v => `<dt>${esc(v.label)} <small>${esc(v.unit)}</small></dt><dd class="mono">${esc(variableDisplay(item.values[v.id], v, mod(item.moduleId).precision))}</dd>`).join('')}</dl></div>` : ''}`;
}
function validateModelVariables(item, m) {
  if (item.values !== undefined && (!item.values || typeof item.values !== 'object' || Array.isArray(item.values))) throw Error('型号变量数据不完整。');
  const values = Object.fromEntries(m.variables.filter(instanceWritable).map(v => [v.id, v.origin === 'parameter' ? item.params[v.param]
    : item.values && v.id in item.values ? item.values[v.id] : m.values[v.id]]));
  validateInstanceEdits(null, values, m);
}

// Local interaction model. No solver, user-code execution, network or hardware access.
const uid = prefix => `${prefix}-${++state.serial}`;
const windowKey = id => `${state.activeProject}:${id}`;
const field = (name, label, value = '', attrs = '') => `<label class="field"><span>${esc(label)}</span><input name="${name}" aria-label="${esc(label)}" value="${esc(value)}" ${attrs}></label>`;
const selectField = (name, label, items, value) => `<label class="field"><span>${esc(label)}</span><select name="${name}" aria-label="${esc(label)}">${items.map(([id, text]) => option(id, text, value)).join('')}</select></label>`;
const isIdentifier = value => /^[A-Za-z_][A-Za-z0-9_]{0,47}$/.test(value);
function numeric(value, min = -1e12, max = 1e12, integer = false) {
  if (value === '' || value === null || !Number.isFinite(Number(value))) throw Error('请输入有效数值。');
  const n = Number(value);
  if (n < min || n > max || integer && !Number.isInteger(n)) throw Error(`请输入 ${min} 至 ${max} 之间的${integer ? '整数' : '数值'}。`);
  return n;
}
function readParams(data, kind, prefix = '', definitions = PARAM_DEFS[kind] || []) {
  return Object.fromEntries(definitions.map(f => [f[0], numeric(data[prefix + f[0]], f[3], f[4])]));
}
function paramsFields(kind, values) {
  return (PARAM_DEFS[kind] || []).map(f => field(f[0], `${f[1]} · ${f[2]}`, values[f[0]] ?? f[6], `type="number" min="${f[3]}" max="${f[4]}" step="any" required`)).join('');
}
function retainFocus(renderFn = render) {
  const el = document.activeElement, selection = el?.selectionStart;
  const attrs = el && [...el.attributes].filter(a => a.name.startsWith('data-') || a.name === 'aria-label' || a.name === 'name');
  const ancestor = el?.closest('[data-float-id]')?.dataset.floatId;
  const scrollKey = e => `${e.closest('[data-float-id]')?.dataset.floatId || ''}:${e.id || e.className}`;
  const scrolls = [...root.querySelectorAll('#page,.editor-content,.table-wrap,.float-body,.instance-table-wrap')].map(e => [scrollKey(e), e.scrollTop, e.scrollLeft]);
  renderFn();
  for (const e of root.querySelectorAll('#page,.editor-content,.table-wrap,.float-body,.instance-table-wrap')) {
    const old = scrolls.find(s => s[0] === scrollKey(e));
    if (old) { e.scrollTop = old[1]; e.scrollLeft = old[2]; }
  }
  if (!attrs?.length) return;
  const scope = ancestor ? root.querySelector(`[data-float-id="${CSS.escape(ancestor)}"]`) : root;
  const next = [...(scope?.querySelectorAll('input,textarea,select,button') || [])].find(e => e.tagName === el.tagName && attrs.every(a => e.getAttribute(a.name) === a.value));
  next?.focus({ preventScroll: true });
  if (typeof selection === 'number' && next?.setSelectionRange) try { next.setSelectionRange(selection, selection); } catch {}
}
function openDialog(title, description, body, onSubmit = null, submitLabel = '确定', wide = false) {
  modal = { title, description, body, onSubmit, submitLabel, wide, returnFocus: document.activeElement };
  renderDialog(true);
}
function renderDialog(focus = false) {
  const layer = document.getElementById('dialog-layer');
  if (!modal) { layer.innerHTML = ''; return; }
  if (!focus && layer.firstElementChild) return;
  layer.innerHTML = `<div class="dialog-backdrop"><form class="dialog${modal.wide ? ' wide' : ''}" id="dialog-form" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header class="dialog-head"><div class="grow"><h2 id="dialog-title">${esc(modal.title)}</h2><p>${esc(modal.description)}</p></div>${ibtn('close-dialog', '关闭弹窗', 'X')}</header><div class="dialog-body"><div id="dialog-error" class="dialog-error" role="alert" hidden></div>${modal.body}</div><footer class="dialog-footer">${btn('close-dialog', modal.onSubmit ? '取消' : '关闭')}${modal.onSubmit ? `<button class="btn primary" type="submit">${esc(modal.submitLabel)}</button>` : ''}</footer></form></div>`;
  // Initial focus runs a frame later; skip it once the user (or a test) has already focused a
  // field in this dialog, otherwise fast typing lands in the first field instead.
  if (focus) requestAnimationFrame(() => { if (!layer.contains(document.activeElement)) (layer.querySelector('input:not([type=hidden]),select,textarea') || layer.querySelector('button'))?.focus(); });
}
function closeDialog() {
  const returnFocus = modal?.returnFocus;
  modal = null;
  document.getElementById('dialog-layer').innerHTML = '';
  if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
}
function confirmChange(title, text, callback, label = '确认') {
  openDialog(title, text, '', () => { callback(); }, label);
}
function diffMarkup(rows) {
  return `<div class="table-wrap"><table class="diff-table"><thead><tr><th>项目</th><th>当前值</th><th>应用后</th></tr></thead><tbody>${rows.map(([label, before, after]) => `<tr><td>${esc(label)}</td><td class="before">${esc(Array.isArray(before) ? before.join(', ') : before)}</td><td class="after">${esc(Array.isArray(after) ? after.join(', ') : after)}</td></tr>`).join('') || '<tr><td colspan="3">没有参数差异。</td></tr>'}</tbody></table></div>`;
}
function checkChannels(m) {
  const used = new Set(), errors = [];
  for (const c of m.channels.filter(c => c.enabled)) {
    const a = m.ports.find(p => p.id === c.input), b = m.ports.find(p => p.id === c.output);
    if (!a || !b) { errors.push(`${c.name}：请选择完整的入口和出口。`); continue; }
    if (a.direction !== 'in' || b.direction !== 'out') errors.push(`${c.name}：输入输出方向不匹配。`);
    if (a.domain !== b.domain) errors.push(`${c.name}：两端类型不同。`);
    for (const p of [a, b]) { if (used.has(p.id)) errors.push(`${p.name} 重复绑定了启用通路。`); used.add(p.id); }
  }
  return errors;
}
function validateBank(m, bank) {
  for (const v of m.variables.filter(v => v.writable)) {
    const value = bank[v.id], arr = v.type.endsWith('[8]');
    if (arr && (!Array.isArray(value) || value.length !== 8)) throw Error(`${v.name} 必须含 8 项。`);
    for (const n of arr ? value : [value]) numeric(n, -1e12, 1e12, v.type.startsWith('int'));
    const f = (m.manifest ? manifestFields(m.manifest) : PARAM_DEFS[m.kind] || []).find(f => f[0] === v.param);
    if (f) numeric(value, f[3], f[4]);
  }
  numeric(bank['system:step'], 1, 10000, true);
  const form = bank['system:form'], mix = bank['system:mix'];
  const fluids = form.filter(Boolean);
  if (!fluids.length || new Set(fluids).size !== fluids.length || fluids.some(id => !FLUIDS.some(f => f[2] === id))) throw Error('请选择不重复的示例工质编号；0 表示空项。');
  mix.forEach((n, i) => { numeric(n, 0, 1); if (!form[i] && n !== 0) throw Error('空工质项的质量比例必须为 0。'); });
  if (Math.abs(mix.reduce((a, b) => a + b, 0) - 1) > 1e-6) throw Error('工质质量比例之和必须为 1，可先点击“归一化”。');
}
function refreshPortVariables(m) {
  const generated = variablesFor(m).filter(v => v.origin === 'port');
  const old = new Map(m.variables.map(v => [v.id, v]));
  m.variables = generated.map(v => old.has(v.id) ? { ...old.get(v.id), name: v.name, label: v.label } : v).concat(m.variables.filter(v => v.origin !== 'port'));
  for (const values of [m.values, ...m.banks]) {
    for (const v of m.variables) if (!(v.id in values)) values[v.id] = clone(v.value);
    for (const key of Object.keys(values)) if (!m.variables.some(v => v.id === key)) delete values[key];
  }
}
function showBankApplication() {
  const m = mod(), bank = ui.bank;
  validateBank(m, m.banks[bank]);
  const differences = bankDiff(m, bank);
  openDialog(`应用库值 ${bank + 1} 到模块当前值`, `${m.name} · ${m.bankNames[bank]}。本次修改测试初值，项目实例单独应用型号。`, diffMarkup(differences.map(v => [v.label, m.values[v.id], m.banks[bank][v.id]])), () => {
    validateBank(m, m.banks[bank]);
    for (const v of m.variables.filter(v => v.writable)) m.values[v.id] = clone(m.banks[bank][v.id]);
    markDirty(m); render(); msg('库值已应用到模块当前值。');
  }, '应用到当前值', true);
}
function createModelDialog(existingId) {
  const existing = existingId && model(existingId), m = existing ? mod(existing.moduleId) : mod();
  if (!existing) validateBank(m, m.banks[ui.bank]);
  const values = existing?.params || Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.banks[ui.bank]['param:' + f[0]]]));
  openDialog(existing ? '保存型号新版本' : '保存为设备型号', `${m.name} · ${existing ? '已插入的项目设备不会自动更新。' : `来源：库值 ${ui.bank + 1} · ${m.bankNames[ui.bank]}`}`, `<div class="fields">${field('name', '型号名称', existing?.name || `${m.name} · ${m.bankNames[ui.bank]}`, 'required maxlength="60"')}${field('description', '说明 / 版本备注', existing?.description || '', 'maxlength="160"')}${paramsFields(m.kind, values)}</div>`, data => {
    const name = data.name.trim(); if (!name) throw Error('型号名称不能为空。');
    if (state.models.some(v => v.id !== existingId && v.moduleId === m.id && v.name === name)) throw Error('此模块已有同名型号。');
    const params = readParams(data, m.kind), note = data.description.trim() || '参数更新';
    if (existing) {
      existing.version++; existing.name = name; existing.description = note; existing.params = params;
      if (existing.values) for (const [key, value] of Object.entries(params)) existing.values['param:' + key] = value;
      existing.versions.push({ version: existing.version, note, params: clone(params), ...(existing.values ? { values: clone(existing.values) } : {}) });
      state.selectedModel = existing.id;
    } else {
      const id = uid('model');
      state.models.push({ id, moduleId: m.id, name, description: note, version: 1, moduleVersion: m.version, params, values: clone(m.banks[ui.bank]), bank: ui.bank + 1, archived: false, versions: [{ version: 1, note, params: clone(params) }] });
      for (const [key, value] of Object.entries(params)) state.models.at(-1).values['param:' + key] = value;
      state.selectedModel = id;
    }
    markDirty(); navigate('models'); msg(existing ? '新版本已保存到型号草稿。' : '新型号已加入型号库。');
  }, existing ? '保存新版本' : '保存型号');
}
function stageModel(n, id) {
  const item = model(id);
  if (!item || item.archived || item.moduleId !== n.moduleId) throw Error('请选择同一模块的在用型号。');
  n.draft = {...n.draft, ...clone(item.params)}; n.draftModelId = id; n.draftModelVersion = item.version;
  const data = ensureInstanceVariables(n);
  for (const v of moduleOf(n).variables.filter(v => v.origin === 'custom' && instanceWritable(v))) data.draft[v.id] = clone(item.values?.[v.id] ?? data.values[v.id]);
  markDirty(project());
}
function applyInstanceDialog(n) {
  const values = instanceEdits(n);
  const rows = moduleOf(n).variables.filter(v => instanceWritable(v) && !sameValue(instanceVariableValue(n, v), values[v.id])).map(v => [`${v.label} · ${v.unit}`, instanceVariableValue(n, v), values[v.id]]);
  for (const p of deviceParamSpecs(n).filter(p => p.value_type !== 'number' && !sameValue(n.draft[p.id], n.params[p.id])))
    rows.push([`${p.label} · ${PARAM_TYPE_LABELS[p.value_type] || p.value_type}`, parameterValueText(n.params[p.id], p.value_type), parameterValueText(n.draft[p.id], p.value_type)]);
  if (n.draftModelId) rows.unshift(['来源型号', `${model(n.modelId)?.name || '自定义'} v${n.modelVersion || 1}`, `${model(n.draftModelId)?.name} v${n.draftModelVersion}`]);
  openDialog(`应用到 ${n.id} · ${n.name}`, '保存保留草稿；确认应用后参数生效，并在运行事件中记录时间。', diffMarkup(rows), async () => {
    validateInstanceEdits(n, values);
    if (project().run.live) { try { await engine.applyParameters(project(), n); } catch (error) { msg(error.message, true); } return; }
    remember(); commitInstanceEdits(n, values);
    if (n.draftModelId) { n.modelId = n.draftModelId; n.modelVersion = n.draftModelVersion; }
    n.draftModelId = null; n.draftModelVersion = null;
    project().run.events.push({ t: project().run.time, kind: 'parameters', text: `${n.id} 参数已应用：${rows.map(([label, , value]) => `${label}=${value}`).join('，')}` });
    markDirty(project()); render(); msg(`${n.id} 参数已应用 · ${clockLabel(project().run.time)}`);
  }, '确认应用', true);
}
function windowBounds(f) {
  const p = page.getBoundingClientRect(), minW = Math.min(320, p.width - 16);
  f.w = clamp(f.w || 440, minW, p.width - 16);
  f.h = clamp(f.h || 520, Math.min(270, p.height - 16), p.height - 16);
  f.x = clamp(f.x ?? p.right - f.w - 20, p.left + 8, p.right - f.w - 8);
  f.y = clamp(f.y ?? p.top + 28, p.top + 8, p.bottom - (f.minimized ? 46 : f.h) - 8);
  return f;
}
function rememberWindow(f) { state.windowPositions ||= {}; state.windowPositions[windowKey(f.id)] = { x: f.x, y: f.y, w: f.w, h: f.h, pinned: f.pinned, docked: !!f.docked }; }
function openDevice(id) {
  if (!instance(id)) return;
  ui.selectedNode = id;
  let f = ui.floats.find(f => f.id === id);
  if (!f) { f = { id, tab: 'parameters', ...(state.windowPositions?.[windowKey(id)] || {}), order: ++ui.floatSerial }; ui.floats.push(f); }
  if (f.docked) for (const other of ui.floats) if (other !== f && other.docked) { other.docked = false; rememberWindow(other); }
  f.minimized = false; f.order = ++ui.floatSerial; ui.frontId = id;
  syncDeviceSelection(); renderFloats();
}
const PARAM_TYPE_LABELS = {number:'数值', boolean:'布尔', text:'文本', curve:'曲线'};
function deviceExtraParamRows(n, m) {
  const specs = deviceParamSpecs(n).filter(p => p.value_type !== 'number');
  if (!specs.length) return '';
  const rows = specs.map(p => {
    const draft = n.draft[p.id], current = n.params[p.id], edited = !sameValue(draft, current);
    const text = parameterValueText(draft, p.value_type);
    const editor = p.value_type === 'boolean'
      ? `<label class="check-label"><input type="checkbox" data-instance-param="${esc(p.id)}" data-param-type="boolean" data-id="${n.id}" aria-label="${esc(n.id)} ${esc(p.label)}草稿" ${draft === true ? 'checked' : ''}>启用</label>`
      : p.value_type === 'curve'
        ? `<textarea class="cell-input mono" rows="3" data-instance-param="${esc(p.id)}" data-param-type="curve" data-id="${n.id}" aria-label="${esc(n.id)} ${esc(p.label)}草稿">${esc(text)}</textarea>`
        : `<input type="text" data-instance-param="${esc(p.id)}" data-param-type="text" data-id="${n.id}" value="${esc(text)}" aria-label="${esc(n.id)} ${esc(p.label)}草稿" maxlength="200">`;
    return `<div class="parameter-row${edited ? ' edited' : ''}"><div class="param-title"><div class="parameter-label-actions"><strong>${esc(p.label)}</strong>${badge(PARAM_TYPE_LABELS[p.value_type] || p.value_type)}</div><small>当前 ${esc(parameterValueText(current, p.value_type)) || '—'}</small></div>${editor}</div>`;
  }).join('');
  return `<div class="row spread" style="margin-top:18px"><strong>其他参数</strong>${badge('非数值类型')}</div><p class="muted" style="font-size:12px;margin:0 0 10px">布尔、文本和曲线参数按各自类型编辑；曲线使用 JSON 点对数组。</p>${rows}`;
}
function floatBody(f, n) {
  const m = moduleOf(n), run = project().run;
  if (f.tab === 'variables') return instanceVariablesBody(f, n);
  if (f.tab === 'results') return `<div class="notice">${icon('Info')}主系统 · ${statusText(run)} · ${clockLabel(run.time)}</div><div class="metric-row"><div class="metric"><span>质量流量 · kg/s</span><strong>${number(flowFor(n), 3)}</strong></div><div class="metric"><span>温度 · °C</span><strong>${number(run.values.temperature, 1)}</strong></div></div>${btn('device-curve', '将流量加入曲线', 'Activity', `data-id="${n.id}"`)}`;
  if (f.tab === 'connections') return `<div class="stack">${m.ports.map(p => { const pg = project().pages.find(pg => pg.nodes.some(x => x.id === n.id)), edge = pg.edges.find(e => e[1] === n.id && e[2] === p.id || e[3] === n.id && e[4] === p.id); return `<div class="list-row" style="padding:10px 0"><div class="grow"><strong>${esc(p.name)} · ${esc(p.label)}</strong><small>${DOMAINS[p.domain].label} · ${edge ? esc(edge[1] + ' ↔ ' + edge[3]) : '未连接'}</small></div>${edge ? btn('delete-edge', '断开', 'X', `data-id="${edge[0]}"`, 'small') : badge('空闲')}</div>`; }).join('')}</div>`;
  return `<label class="field"><span>设备名称</span><input data-instance-name="${n.id}" value="${esc(n.name)}" aria-label="${n.id} 设备名称" maxlength="50"></label><div class="field" style="margin-top:13px"><span>选择型号 → 进入待应用草稿</span><select data-instance-model="${n.id}" aria-label="${n.id} 设备型号">${option('', '自定义参数', n.draftModelId || n.modelId)}${state.models.filter(v => v.moduleId === m.id && !v.archived).map(v => option(v.id, v.name + ' · v' + v.version, n.draftModelId || n.modelId)).join('')}</select></div><div class="row spread" style="margin-top:12px"><strong>常用参数</strong><span class="badge ${pendingCount(n) ? 'warn' : 'good'}" data-pending-for="${n.id}">${pendingCount(n)} 项待应用</span></div>${paramDefs(n).filter(f => m.variables.find(v => v.param === f[0])?.display !== false).map(f => `<div class="parameter-row${n.draft[f[0]] !== n.params[f[0]] ? ' edited' : ''}"><div class="param-title"><div class="parameter-label-actions"><strong>${f[1]}</strong>${ibtn('device-variables', '查看 ' + f[1] + ' 的全部变量', 'Table2', `data-id="${n.id}" data-variable="param:${f[0]}"`)}</div><small>当前 ${number(n.params[f[0]], f[0] === 'opening' ? 0 : 2)} ${f[2]}</small>${quickFieldMarkup(n, m, f)}</div><input type="number" step="any" min="${f[3]}" max="${f[4]}" data-instance-param="${f[0]}" data-id="${n.id}" value="${n.draft[f[0]]}" aria-label="${n.id} ${f[1]}草稿" ${m.quickParam === f[0] && m.quickType === "display" ? "readonly" : ""}><span class="muted">${f[2]}</span></div>`).join('') || '<p class="muted" style="margin:14px 0">此模块没有常用可调参数。</p>'}${deviceExtraParamRows(n, m)}<div class="row wrap" style="margin-top:16px">${btn('device-definition', '完整模块定义', 'Box', `data-id="${n.id}"`, 'small ghost')}${btn('save-instance-model', '保存为型号', 'Database', `data-id="${n.id}"`, 'small')}</div>`;
}
function quickCanvasMarkup(n, m) {
  const def = paramDefs(n).find(f => f[0] === m.quickParam);
  if (!def || m.variables.find(v => v.param === def[0])?.display === false) return '';
  return `<g data-quick-node="${n.id}" role="button" tabindex="0" aria-label="修改 ${esc(n.name + ' ' + def[1])}"><rect class="quick-param" x="-35" y="68" width="70" height="20" rx="4"/><text class="quick-param-label" x="0" y="82" text-anchor="middle">${number(n.params[def[0]], def[0] === 'opening' ? 0 : 1)} ${esc(def[2])}${m.quickType === 'display' ? '' : ' ▾'}</text></g>`;
}
function portStubs(n) {
  return `<g transform="rotate(${n.rotation || 0})">${moduleOf(n).ports.map(p => { const d = portOffset(n, p); return `<path d="M ${d.x} ${d.y} H 0 V 0" fill="none" stroke="var(--${DOMAINS[p.domain].color})" stroke-width="1.3"/>`; }).join('')}</g>`;
}
function quickFieldMarkup(n, m, f) {
  if (m.quickParam !== f[0]) return '';
  if (m.quickType === 'slider') return `<input type="range" data-instance-param="${f[0]}" data-id="${n.id}" min="${f[3]}" max="${f[4]}" step="${f[5]}" value="${n.draft[f[0]]}" aria-label="${n.id} ${f[1]}滑块">`;
  if (m.quickType === 'switch') return `<label class="check-label" style="margin-top:6px"><input type="checkbox" data-instance-switch="${f[0]}" data-id="${n.id}" ${n.draft[f[0]] > f[3] ? 'checked' : ''}>切换 ${f[3]} / ${f[4]} ${esc(f[2])}</label>`;
  return '';
}
function renderFloats() {
  const layer = document.getElementById('floating-layer');
  syncDockLayout();
  let html = '';
  if (ui.route === 'workbench') html = ui.floats.filter(f => instance(f.id)).map(f => {
    const bounds = isDocked(f) ? dockWindowBounds(f) : windowBounds(f); const n = instance(f.id);
    const bank = f.tab === 'variables' ? variableWindowState(f).source : -1;
    const apply = bank < 0
      ? btn('apply-instance', '预览并应用', 'Check', `data-id="${n.id}" ${pendingCount(n) ? '' : 'disabled'}`, 'primary small')
      : btn('apply-instance-bank', `应用库值 ${bank + 1}`, 'Check', `data-id="${n.id}" data-bank="${bank}" ${instanceBankDiff(n, bank).length ? '' : 'disabled'}`, 'primary small');
    return `<section class="floater${isDocked(f) ? ' docked' : ''}${ui.frontId === f.id ? ' front' : ''}${f.minimized ? ' minimized' : ''}${f.tab === 'variables' ? ' variables-floater' : ''}" role="region" aria-label="${esc(n.id + ' 设备参数')}" data-float-id="${f.id}" style="left:${bounds.x}px;top:${bounds.y}px;width:${bounds.w}px;height:${f.minimized ? 46 : bounds.h}px;z-index:${50 + (f.pinned ? 50 : 0) + f.order % 40}">
      <header class="float-head" data-float-move="${f.id}">${icon('SlidersHorizontal')}<strong class="float-title">${esc(n.id + ' · ' + n.name)}</strong>${ibtn('float-dock', f.docked ? '取消停靠' : '停靠到右侧', f.docked ? 'ExternalLink' : 'Columns2', `data-id="${f.id}" aria-pressed="${!!f.docked}" ${innerWidth < 1000 && !f.docked ? 'hidden' : ''}`)}${ibtn('float-pin', '置顶窗口', 'Pin', `data-id="${f.id}" aria-pressed="${!!f.pinned}"`)}${ibtn('float-max', '最大化或还原', 'Maximize2', `data-id="${f.id}"`)}${ibtn('float-min', f.minimized ? '还原窗口' : '收起窗口', f.minimized ? 'ChevronDown' : 'Minus', `data-id="${f.id}"`)}${ibtn('float-close', '关闭设备窗口', 'X', `data-id="${f.id}"`)}</header>
      ${f.minimized ? '' : `<nav class="tabs float-tabs" aria-label="设备属性页签">${[['parameters', '参数与型号'], ['variables', '全部变量'], ['results', '运行结果'], ['connections', '连接']].map(([id, label]) => `<button type="button" data-action="float-tab" data-id="${f.id}" data-value="${id}" class="${f.tab === id ? 'active' : ''}" aria-pressed="${f.tab === id}">${label}</button>`).join('')}</nav><div class="float-body">${floatBody(f, n)}</div><footer class="float-footer"><div class="float-save-state grow"><small data-float-save>${state.dirty ? '草稿未保存' : '草稿已保存'}</small><small data-float-keyframe ${replayingKeyFrame(project().run) ? '' : 'hidden'}>回放：显示最近关键帧</small><small data-device-apply-status="${n.id}"></small></div>${btn('save', '保存草稿', 'Save', 'title="保存整个原型；待应用参数保持草稿状态"', 'small')}${apply}</footer><button class="float-resize" data-float-resize="${f.id}" aria-label="调整窗口大小">${icon('Grip')}</button>`}
    </section>`;
  }).join('');
  if (contextMenu) html += `<div class="context-menu" style="left:${contextMenu.x}px;top:${contextMenu.y}px">${deviceContextMarkup(contextMenu.id)}</div>`;
  if (ui.taskDrawer) html += `<section class="task-drawer"><div class="panel-head"><h3>运行任务</h3>${ibtn('tasks', '关闭任务列表', 'X')}</div><div class="panel-body stack">${state.projects.filter(p => ['running', 'paused'].includes(p.run.status)).map(p => `<div class="row"><div class="grow"><strong>${esc(p.name)}</strong><small>${statusText(p.run)} · ${clockLabel(p.run.time)}</small></div>${btn('open-project', '查看', '', `data-id="${p.id}"`, 'small')}${btn('stop-task', '停止', '', `data-id="${p.id}"`, 'small')}</div>`).join('')}<small class="muted">切换页面或关闭查看窗口后，任务继续保留。</small></div></section>`;
  layer.innerHTML = html;
  syncWorkbenchStatus();
  requestAnimationFrame(() => { resizeCharts(); restoreChartCursor(); });
}
function updateFloatBodies() { retainFocus(renderFloats); }
async function setBench(id, params) {
  if (['running', 'solving'].includes(state.bench.run.status)) throw Error('先停止当前单机测试，再切换被测设备。');
  const m = mod(id);
  if(m.contractDraft !== undefined && !await engine.checkModule(m,true)) { msg('契约未通过校验，请先修正。',true); return; }
  state.bench.moduleId = m.id;
  state.bench.params = params ? clone(params)
    : m.runtime === 'python' ? manifestParamDefaults(m.manifest)
    : Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.values['param:' + f[0]] ?? f[6]]));
  state.bench.run = emptyRun('bench');
  state.bench.run.step = Math.max(.01, (m.values['system:step'] || 100) / 1000);
  markDirty(); navigate('bench');
}
function createModuleExample(id) {
  const m=engine.moduleForInsert(id), channel=m.channels.find(c=>c.enabled);
  if (m.ports.length !== 2 || m.channels.filter(c=>c.enabled).length !== 1) {
    const channels=m.channels.filter(c=>c.enabled),used=channels.flatMap(c=>[c.input,c.output]);
    if(!channels.length||new Set(used).size!==used.length||used.length!==m.ports.length)throw Error('此模块使用共享端口，请在项目画布连接实际拓扑。');
    const draft=state.modules.find(module=>module.id===id),node=makeInstance('V1',m.id,m.name,540,220,manifestParamDefaults(m.manifest));
    const pg={id:'main',name:'多通路模块验收',zoom:1,pan:[0,0],nodes:[node],edges:[]};
    channels.forEach((c,index)=>{
      const condition=draft?.testConditions?.channel_boundaries?.[c.id] || {};
      const a='B'+(index*2+1),b='B'+(index*2+2),temperature=c.id.includes('hot')?320:290;
      pg.nodes.push(makeInstance(a,'source',c.name+'入口',130,120+index*230,{pressure:(condition.inlet_pressure_pa || 250000)/1000,temperature:(condition.inlet_temperature_k || temperature)-273.15}));
      pg.nodes.push(makeInstance(b,'source',c.name+'出口',890,120+index*230,{pressure:(condition.outlet_pressure_pa || 120000)/1000,temperature:(condition.outlet_temperature_k || temperature)-273.15}));
      pg.edges.push(['in'+index,a,'out0','V1',c.input],['out'+index,'V1',c.output,b,'out0']);
    });
    const p=makeProject(uid('project'),m.name+' · 多通路验收','各通路独立边界',pg);p.moduleSnapshots={[m.id]:clone(m)};
    p.solver.duration=1;p.solver.dt=.1;state.projects.push(p);normalizeState();markDirty(p);openProject(p.id);return;
  }
  if (state.projects.length >= 20) throw Error('项目数量已达到上限。');
  const params=Object.fromEntries((m.parameterDefs || PARAM_DEFS[m.kind] || []).map(f=>[f[0],f[6]]));
  const pg={id:'main',name:'模块管网验收',zoom:1,pan:[0,0],nodes:[
    makeInstance('B1','source','入口压力',130,225,{pressure:250}),
    makeInstance('L1','pipe','上游管道',380,225,{length:30,diameter:40}),
    makeInstance('V1',m.id,m.name,630,225,params),
    makeInstance('B2','source','出口压力',900,225,{pressure:120})],
    edges:[['e1','B1','out0','L1','in0'],['e2','L1','out0','V1',channel.input],['e3','V1',channel.output,'B2','out0']]};
  const conditions=state.modules.find(module=>module.id===id)?.testConditions;
  if(conditions?.inlet_pressure_pa)pg.nodes[0].params.pressure=conditions.inlet_pressure_pa/1000;
  if(conditions?.outlet_pressure_pa)pg.nodes[3].params.pressure=conditions.outlet_pressure_pa/1000;
  pg.nodes[0].draft=clone(pg.nodes[0].params);pg.nodes[3].draft=clone(pg.nodes[3].params);
  const p=makeProject(uid('project'),m.name+' · 管网验收','压力源 → 管道 → Python 模块 → 出口',pg);
  if(m.frozen) p.moduleSnapshots={[m.id]:clone(m)};
  p.solver.duration=1; p.solver.dt=.1;
  state.projects.push(p); normalizeState(); markDirty(p); ui.showLibrary=true; openProject(p.id);
}
function newInstance(moduleId, point, selectedModel) {
  const m = engine.bindModule(project(),moduleId), pg = activePage();
  if (pg.nodes.length >= 64) throw Error('当前原型每张画布最多演示 64 台设备。');
  remember();
  const node = makeInstance(uid(m.kind === 'valve' ? 'V' : m.kind === 'pump' ? 'P' : 'D'), m.kind, m.name, point?.x ?? 250 + pg.nodes.length % 5 * 110, point?.y ?? 140 + Math.floor(pg.nodes.length / 5) * 100);
  node.moduleId = m.id;
  if (m.runtime === 'python') { node.params=manifestParamDefaults(m.manifest); node.draft=clone(node.params); }
  if (selectedModel) { node.params = clone(selectedModel.params); node.draft = clone(node.params); node.modelId = selectedModel.id; node.modelVersion = selectedModel.version; }
  else if (m.id !== m.kind) { node.modelId = null; node.params = Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.values['param:' + f[0]] ?? f[6]])); node.draft = clone(node.params); }
  ensureInstanceVariables(node, m);
  if (selectedModel?.values) for (const v of m.variables.filter(v => v.origin === 'custom')) {
    const value = clone(selectedModel.values[v.id] ?? node.variableState.values[v.id]);
    node.variableState.values[v.id] = clone(value); node.variableState.draft[v.id] = clone(value); node.variableState.banks[0][v.id] = clone(value);
  }
  pg.nodes.push(node); engine.pinProject(project()); ui.selectedNode = node.id; ui.placing = null; if (innerWidth <= 500) ui.showLibrary = false;
  markDirty(project()); render(); return node;
}
function validateNetwork(p = project()) {
  const errors = [];
  if (!p.pages.some(pg => pg.nodes.length)) errors.push({ text: '项目没有设备。' });
  for (const pg of p.pages) {
    const used = new Set();
    for (const [id, na, pa, nb, pb] of pg.edges) {
      const a = endpoint(pg, na, pa), b = endpoint(pg, nb, pb);
      if (!a || !b) { errors.push({ text: `${id}：连接端口不存在。`, page: pg.id, node: na }); continue; }
      if (a.port.domain !== b.port.domain) errors.push({ text: `${id}：两端领域不一致。`, page: pg.id, node: na });
      for (const key of [na + ':' + pa, nb + ':' + pb]) { if (used.has(key)) errors.push({ text: `${key}：端口重复连接。`, page: pg.id, node: na }); used.add(key); }
    }
    for (const n of pg.nodes) {
      const m = moduleOf(n);
      for (const p of m.ports) if (p.required !== false && !used.has(n.id + ':' + p.id)) errors.push({ text: `${n.id} · ${p.label} 尚未连接。`, page: pg.id, node: n.id });
      for (const text of checkChannels(m)) errors.push({ text: `${n.id} · ${text}`, page: pg.id, node: n.id });
    }
  }
  return errors;
}
function connectPort(nodeId, portId) {
  const pg = activePage(), next = endpoint(pg, nodeId, portId);
  if (!next) return;
  const used = pg.edges.some(e => e[1] === nodeId && e[2] === portId || e[3] === nodeId && e[4] === portId);
  if (used) throw Error('此端口已经连接。请先断开原连接，或使用连接节点分支。');
  if (!ui.connecting) { ui.connecting = { nodeId, portId }; render(); return; }
  const first = ui.connecting;
  if (first.nodeId === nodeId) { ui.connecting = null; render(); return; }
  const previous = endpoint(pg, first.nodeId, first.portId);
  if (previous.port.domain !== next.port.domain) throw Error('两端的物理类型必须相同。');
  if (next.port.domain !== 'fluid' && previous.port.direction === next.port.direction) throw Error('此类端口需要输入与输出相连。');
  remember(); pg.edges.push([uid('edge'), first.nodeId, first.portId, nodeId, portId]); ui.connecting = null;
  markDirty(project()); render(); msg('连接已建立。');
}
function deleteNode(id) {
  const owner=project(),pg=owner.pages.find(pg=>pg.nodes.some(n=>n.id===id));if(!pg)return;
  const references=coldStorage.couplingReferences(owner,[id]);
  const key=projectParameterKey(owner);
  if(references.length)coldStorage.assertCouplingIdle(owner);
  const remove=()=>{
    if(project()!==owner)throw Error('项目已切换，请重新选择要删除的设备。');
    if(projectParameterKey(owner)!==key)throw Error('确认期间项目发生变化，请重新选择要删除的设备。');
    const targetPage=owner.pages.find(page=>page.nodes.some(node=>node.id===id));
    if(!targetPage)throw Error('设备已不存在，请重新选择。');
    const links=coldStorage.couplingReferences(owner,[id]);
    if(links.length)coldStorage.assertCouplingIdle(owner);
    remember();targetPage.nodes=targetPage.nodes.filter(n=>n.id!==id);targetPage.edges=targetPage.edges.filter(e=>e[1]!==id&&e[3]!==id);
    if(links.length){
      const removed=new Set(links.map(link=>link.id));
      owner.thermalCouplings=owner.thermalCouplings.filter(link=>!removed.has(link.id));
      coldStorage.syncCouplingCharts(owner);
    }
    ui.floats=ui.floats.filter(f=>f.id!==id);ui.selectedNode='';ui.connecting=null;
    markDirty(owner);persistLocal();render();msg(links.length?'设备、关联连接与热耦合已删除，可撤销。':'设备与关联连接已删除，可撤销。');
  };
  if(references.length)confirmChange('删除热耦合设备',`删除 ${id} 将同时解除热耦合 ${references.map(link=>link.id).join('、')}。相关当前曲线也会移除，已保存运行记录保留。`,remove,'删除并解除耦合');
  else remove();
}
function deleteEdge(id) { remember(); project().pages.forEach(pg => pg.edges = pg.edges.filter(e => e[0] !== id)); ui.selectedEdge = ''; markDirty(project()); render(); }
function copyDevice(id = ui.selectedNode) { const n = instance(id); if (n) { ui.clipboard = clone(n); msg(`${n.id} 已复制；Ctrl+V 粘贴。`); } }
function pasteDevice() {
  if (!ui.clipboard) return;
  remember(); const n = clone(ui.clipboard); n.id = uid('D'); n.name += ' 副本'; n.x += 60; n.y += 60;
  activePage().nodes.push(n); ui.selectedNode = n.id; markDirty(project()); render();
}
function commandRun(scope, command, projectId) { return engine.command(scope, command, projectId); }
function refreshLive() {
  coldStorage.refresh(project());
  const controlLive=document.getElementById('control-live');if(controlLive)controlLive.textContent=controlLiveValues();
  if (ui.route === 'curves') {
    const run = currentChartRun();
    const items = [['main-chart', ['q', 'a', 'b'], 'main-flow-chart'], ['pressure-chart', ['pressure'], 'pressure-line'], ['temperature-chart', ['temperature'], 'temperature-line']];
    for (const [id, keys, chartId] of items) { const e = document.getElementById(id); if (e) e.innerHTML = chartSvg(run.history, keys, chartId, id === 'main-chart' && state.charts.compare); }
    updateExtraCharts();
    const readout = document.getElementById('main-flow-chart-readout');
    if (readout && !ui.pinnedChart) readout.textContent = `${clockLabel(run.time)} · 主管 ${number(run.values?.q ?? run.history.at(-1)?.q, 3)} kg/s`;
  }
  if (ui.route === 'workbench') refreshWorkbenchChart();
  restoreChartCursor();
  if (ui.route === 'workbench' && !pointer) {
    const svg = document.getElementById('network'); if (svg) svg.innerHTML = networkMarkup(activePage()); paintCanvasInspection();
    for (const f of ui.floats.filter(f => f.tab === 'results' && !f.minimized)) {
      const body = root.querySelector(`[data-float-id="${f.id}"] .float-body`); if (body) body.innerHTML = floatBody(f, instance(f.id));
    }
    for (const f of ui.floats.filter(f => f.tab === 'variables' && !f.minimized)) if (instance(f.id)) refreshInstanceVariableReadouts(f, instance(f.id));
  }
  root.querySelectorAll('[data-live-time]').forEach(el => el.textContent = clockLabel(project().run.time));
  syncChrome();
}
function runChartSnapshot(owner) {
  const current=state.charts.extra.filter(binding=>binding.projectId===owner.id);
  const original=owner.run.chartBindings||(owner.run.parameterKey===projectParameterKey(owner)?current:[]);
  return clone(current.filter(binding=>!isCouplingChart(binding)).concat(original.filter(isCouplingChart)));
}
function recordRun(scope) {
  const owner = scope === 'bench' ? state.bench : project(), run = owner.run;
  if (run.history.length < 1) throw Error('先运行或单步，生成数据后再保存记录。');
  const name = scope === 'bench' ? mod(owner.moduleId).name + ' · 独立测试' : owner.name + ' · ' + clockLabel(run.time);
  const id = uid('RECORD');
  state.records.unshift({ id, name, projectId: scope === 'bench' ? null : owner.id, projectName: scope === 'bench' ? mod(owner.moduleId).name + ' · 单机测试' : owner.name, moduleId: scope === 'bench' ? owner.moduleId : null, scope, status: run.status, mode: scope === 'bench' ? '单机测试' : owner.solver.mode === 'steady' ? '稳态' : '动态', time: run.time, history: clone(run.history), events: clone(run.events), params: clone(scope === 'bench' ? owner.params : Object.fromEntries(owner.pages.flatMap(pg => pg.nodes).map(n => [n.id, n.params]))), boundary: scope === 'bench' ? clone(owner.boundary) : null, sample: run.source !== 'engine', source: run.source, chartBindings: scope === 'bench' ? [] : runChartSnapshot(owner) });
  state.records = state.records.slice(0, 30); ui.selectedRecord = id; markDirty(); navigate('runs'); msg('运行快照已记录；保存原型后可重新打开。');
}
function showDiagnostics(issues = []) {
  openDialog('连接与定义检查', issues.length ? `${issues.length} 项需要检查，点击可定位设备。` : '后端结构检查通过，可以提交水力求解。', issues.length ? `<div class="stack">${issues.map(x => btn('locate-issue', esc(x.text), 'Info', `data-id="${x.node || ''}" data-page="${x.page || ''}"`, 'ghost')).join('')}</div>` : `<div class="notice good">${icon('CheckCircle2')}端口、内部通路、参数范围及各子网络压力参考均通过检查。</div>`, null, '', true);
}
function previewCode(kind = 'runtime', build = false) {
  if (mod().runtime === 'python') { engine.checkModule(mod()); return; }
  const m = mod(), name = { runtime: '运行代码', header: '公共代码', design: `设计函数 ${ui.designIndex + 1}` }[kind];
  const sources = build ? [['运行代码', m.source.runtime], ['公共代码', m.source.header], ...m.source.design.map((code, i) => [`设计函数 ${i + 1}`, code])] : [[name, kind === 'design' ? m.source.design[ui.designIndex] : m.source[kind]]];
  const checks = sources.map(([label, source]) => { const issue = pythonCodeIssue(source); return issue ? `× ${label}：${issue}` : `✓ ${label}：Python 基础结构检查通过`; });
  if (build) {
    const errors = checkChannels(m);
    checks.push(errors.length ? '× ' + errors.join('\n') : '✓ 端口与通路检查通过', 'Python 调用流程预览：载入公共代码 → 载入运行函数 / 设计函数 → 项目调用');
  } else checks.push(`检查对象：${m.code} / ${name}。`);
  checks.push('仅检查括号与字符串；未进行完整 Python 语法、缩进或算法校验，代码未执行。');
  ui.compileOutput = checks.join('\n');
  const out = document.getElementById('code-output');
  if (out) out.textContent = ui.compileOutput;
  else openDialog('Python 检查与调用预览', m.name, `<pre class="code-preview">${esc(ui.compileOutput)}</pre>`);
}
function previewDesign(i = ui.bank) {
  const m = mod();
  ui.compileOutput = `设计函数 ${i + 1} → 库值 ${i + 1} · ${m.bankNames[i]}\n${pythonCodeIssue(m.source.design[i]) || 'Python 基础结构检查通过。'}\n这是调用流程预览；库值未被修改，代码未执行。`;
  const out = document.getElementById('code-output');
  if (out) out.textContent = ui.compileOutput;
  else openDialog('设计函数调用预览', m.name, `<pre class="code-preview">${esc(ui.compileOutput)}</pre>`);
}
function bindingsForProject() {
  if (!project().bindings) {
    const variables = projectVariables(), temperature = variables.find(v => v.legacyId === 'P1.OUT_TEMP') || variables.find(v => v.legacyId?.endsWith('.OUT_TEMP')), writable = variables.find(v => v.id === 'V1.OPENING') || variables.find(v => v.writable);
    project().bindings = [];
    if (temperature) project().bindings.push({ external: 'Sensor.Temperature', variable: temperature.id, direction: 'read', unit: temperature.unit });
    if (writable) project().bindings.push({ external: 'Control.Parameter', variable: writable.id, direction: 'write', unit: writable.unit });
  }
  return project().bindings;
}
function apiCall(kind = ui.apiKind || 'read') {
  const runId = project().run.id || '{run_id}', keys = ['V1.mass_flow_kg_s', 'V1.param.opening_ratio'];
  if (kind === 'status') return { method: 'GET', path: `/api/v1/runs/${runId}` };
  if (kind === 'set') return { method: 'POST', path: `/api/v1/runs/${runId}/variables`, body: { values: { 'V1.param.opening_ratio': 0.65 }, wait_s: 2 } };
  if (kind === 'stream') return { method: 'WS', path: `/api/v1/runs/${runId}/stream?keys=${keys.join(',')}` };
  return { method: 'GET', path: `/api/v1/runs/${runId}/variables?keys=${keys.join(',')}` };
}
function apiPreview(kind = ui.apiKind || 'read', response = null) {
  const call = apiCall(kind), auth = engine.health?.auth?.required ? ' -H "Authorization: Bearer $FLUIDNET_TOKEN"' : '';
  const path = document.getElementById('api-path'); if (path) path.textContent = call.path;
  const method = path?.previousElementSibling; if (method) method.textContent = call.method;
  const curl = call.method === 'WS' ? `# WebSocket：每个新帧推送一次所选变量，结束时发 {"type":"end"}\n# 浏览器无法设置请求头时，用子协议 fluidnet.bearer.<令牌> 传令牌\nws://${location.host}${call.path}`
    : `curl${auth}${call.body ? ` -H "Content-Type: application/json" -d '${JSON.stringify(call.body)}'` : ''} ${location.origin}${call.path}`;
  const request = document.getElementById('api-request'); if (request) request.textContent = curl;
  const out = document.getElementById('api-response');
  if (out) out.textContent = response ? JSON.stringify(response, null, 2) : call.method === 'GET' ? (project().run.id ? '点击“发送请求”读取当前运行。' : '先运行项目，生成 run_id。') : '写入会改变正在运行的模型，此页只展示请求；需要时在终端执行上面的命令。';
}
async function apiSend() {
  const call = apiCall();
  if (call.method !== 'GET') { apiPreview(); return; }
  if (!project().run.id) throw Error('先运行项目，生成 run_id。');
  const response = await fetch(call.path, { headers: engine.authHeaders() });
  apiPreview(ui.apiKind || 'read', { status: response.status, body: await response.json() });
}
function legacyApiPreview(kind = ui.apiKind || 'read') {
  const value = projectVariables().find(v => v.id === 'V1.OPENING') || projectVariables()[0];
  const info = { project_id: project().id, variable: value?.id || null };
  const out = kind === 'status' ? { run_id: project().run.id || null, status: project().run.status, simulation_time: project().run.time, source: 'prototype' } : kind === 'set' ? { command_id: 'DEMO-CMD-001', variable: value?.id, stages: ['已接收', value?.writable ? '已应用（演示）' : '已拒绝：目标只读'], applied_at: project().run.time, changed_real_value: false } : { ...info, value: value?.value ?? null, unit: value?.unit || '', source: 'prototype' };
  const path = document.getElementById('api-path'); if (path) path.textContent = kind === 'status' ? '/runs/current/status' : kind === 'set' ? '/commands/parameters' : '/variables/' + (value?.id || '{variable}');
  const request = document.getElementById('api-request'); if (request) request.textContent = JSON.stringify(kind === 'set' ? { ...info, value: 65 } : info, null, 2);
  document.getElementById('api-response').textContent = JSON.stringify(out, null, 2);
  const method = path?.previousElementSibling; if (method) method.textContent = kind === 'set' ? 'POST' : 'GET';
}
function addChartVariable(id, label, inline = false) {
  const v = projectVariables().find(v => v.id === id); if (!v) throw Error('变量不属于当前项目或暂未提供采样。');
  let binding = state.charts.extra.find(x => x.projectId === project().id && (x.nodeId === v.nodeId && x.variableId === v.variableId || !x.variableId && v.origin !== 'custom' && x.id === v.legacyId));
  if (!binding) { binding = {}; state.charts.extra.push(binding); }
  const stableId = v.sampleKey;
  Object.assign(binding, { id: stableId, label: label || `${v.device} · ${v.name}`, unit: v.unit, projectId: project().id, nodeId: v.nodeId,
    variableId: v.variableId, identifier: v.identifier, sampleKey: v.sampleKey, legacyId: v.legacyId, legacyFactor: v.legacyFactor, ...engine.observation(instance(v.nodeId),moduleOf(instance(v.nodeId)).variables.find(item=>item.id===v.variableId)) });
  state.charts.source = 'live'; markDirty();
  if (inline) { ui.showChart = true; ui.workbenchChart = stableId; ui.pinnedChart = null; saveUI(); retainFocus(); msg('已加入同屏观察，运行或单步后更新当前值曲线。'); }
  else navigate('curves');
}
function extraVariableValue(row, binding, live=true) {
  if(live&&isCouplingChart(binding)){
    const owner=state.projects.find(p=>p.id===binding.projectId);
    if(!owner?.run.parameterKey||owner.run.parameterKey!==projectParameterKey(owner))return null;
  }
  const id = typeof binding === 'string' ? binding : binding.id;
  if(binding.canonicalKey && row.canonical){
    const value=row.canonical[binding.canonicalKey];
    return Number.isFinite(value)?value/binding.canonicalScale+binding.canonicalOffset:null;
  }
  if(binding.variableId?.startsWith('runtime:') && row.canonical){
    const value=row.canonical[binding.nodeId+'.'+binding.variableId.slice(8)];return Number.isFinite(value)?value:null;
  }
  if (binding.sampleKey) {
    if (row.variableValues) { const value = row.variableValues[binding.sampleKey]; return Number.isFinite(value) ? value : null; }
    const value = binding.legacyId ? row.variables?.[binding.legacyId] : null;
    return Number.isFinite(value) ? value * binding.legacyFactor : null;
  }
  if (Number.isFinite(row.variables?.[id])) return row.variables[id];
  if (id.endsWith('.OUT_FLOW')) return /^[VL]1\./.test(id) ? row.a : /^[VL]2\./.test(id) ? row.b : row.q;
  if (id.endsWith('.OUT_PRE')) return row.pressure;
  if (id.endsWith('.OUT_TEMP')) return row.temperature;
  return null;
}
function chartSvg(history, keys = ['q', 'a', 'b'], id = 'flow-chart', compare = false, options = {}) {
  const measured = document.getElementById(id)?.getBoundingClientRect().width;
  const w = Math.max(200, Math.round(measured || (ui.route === 'bench' ? page.clientWidth - 390 : page.clientWidth - 125)));
  const h = options.compact ? 168 : 270, left = w < 360 ? 42 : 58, right = w - 20, top = 23, bottom = h - 48;
  const rows = history.length ? history : [{ t: 0, q: 0, a: 0, b: 0, pressure: 0, temperature: 0 }, { t: 10, q: 0, a: 0, b: 0, pressure: 0, temperature: 0 }];
  const minT = rows[0].t, maxT = Math.max(minT + .1, rows.at(-1).t);
  const baseline = compare ? (state.records.find(r => r.source === 'engine' && r.projectId === project().id)?.history || []).filter(r => r.t >= minT && r.t <= maxT) : [];
  const values = rows.flatMap(r => keys.map(k => Number(r[k]) || 0)).concat(baseline.map(r => r.q));
  const lo = Math.min(0, ...values), hi = Math.max(1, ...values), padding = (hi - lo) * .12;
  const maxY = hi + padding, minY = lo < 0 ? lo - padding : 0;
  const x = t => left + (t - minT) / (maxT - minT) * (right - left), y = n => bottom - (Number(n) - minY) / (maxY - minY) * (bottom - top);
  const unit = SERIES[keys[0]]?.unit || 'kg/s', visible = keys.filter(k => state.charts.series[k] !== false || id === 'bench-chart');
  const path = (rows, key) => { let active = false; return rows.map(r => { if (!Number.isFinite(r[key])) { active = false; return ''; } const command = active ? 'L' : 'M'; active = true; return `${command} ${x(r.t).toFixed(2)} ${y(r[key]).toFixed(2)}`; }).join(' '); };
  const ticks = w < 420 ? 3 : 4;
  chartRegistry.set(id, { rows, keys: visible, minT, maxT, left, right, top, bottom, y, options });
  return `<svg class="chart" id="${id}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(keys.map(k => SERIES[k]?.name || k).join('、'))}随时间变化，单位 ${esc(unit)}" data-chart="${id}"><text x="5" y="14" class="chart-text">${esc(unit)}</text>${[0, 1, 2, 3, 4].map(i => { const n = minY + (maxY - minY) * i / 4, yy = y(n); return `<line x1="${left}" y1="${yy}" x2="${right}" y2="${yy}" class="chart-grid"/><text x="${left - 9}" y="${yy + 4}" text-anchor="end" class="chart-text">${number(n, maxY > 10 ? 0 : 1)}</text>`; }).join('')}${Array.from({ length: ticks + 1 }, (_, i) => `<text x="${left + i / ticks * (right - left)}" y="${bottom + 20}" text-anchor="${i === 0 ? 'start' : i === ticks ? 'end' : 'middle'}" class="chart-text">${number(minT + (maxT - minT) * i / ticks, 1)}</text>`).join('')}<text x="${right}" y="${h - 6}" text-anchor="end" class="chart-text">时间 · s</text>${visible.map(k => `<path d="${path(rows, k)}" class="chart-line" stroke="var(--${SERIES[k]?.color || 'blue'})"/>`).join('')}${baseline.length ? `<path d="${path(baseline, 'q')}" class="chart-line" stroke="var(--muted)" stroke-dasharray="5 5"/>` : ''}${(options.events || []).filter(e => e.t >= minT && e.t <= maxT).slice(-12).map(e => `<g class="chart-event"><title>${esc(clockLabel(e.t) + ' · ' + e.text)}</title><line x1="${x(e.t)}" x2="${x(e.t)}" y1="${top}" y2="${bottom}" stroke="var(--accent)" stroke-dasharray="3 4" opacity=".65"/><circle cx="${x(e.t)}" cy="${top}" r="3" fill="var(--accent)"/></g>`).join('')}<line data-chart-guide x1="0" x2="0" y1="${top}" y2="${bottom}" stroke="var(--muted)" opacity="0"/>${visible.map(k => `<circle data-hover-mark="${esc(k)}" r="3" fill="var(--${SERIES[k]?.color || 'blue'})" opacity="0"/>`).join('')}<rect x="${left}" y="${top}" width="${right - left}" height="${bottom - top}" fill="transparent" data-chart-hit="${id}" style="cursor:crosshair"/></svg>`;
}
function resizeCharts() {
  for (const svg of root.querySelectorAll('svg[data-chart]')) {
    const data = chartRegistry.get(svg.id); if (!data) continue;
    const html = chartSvg(data.rows, data.keys, svg.id, svg.id === 'main-flow-chart' && state.charts.compare, data.options);
    svg.outerHTML = html;
  }
}
function extraChartsMarkup() {
  const run=currentChartRun(),live=state.charts.source==='live';
  return chartBindingsForRun(run).map((v, i) => {
    const key = 'extra:' + v.id;
    const history = run.history.filter(r => extraVariableValue(r, v,live) !== null).map(r => ({ t: r.t, [key]: extraVariableValue(r, v,live) }));
    SERIES[key] = { name: v.label, unit: v.unit, color: 'blue' };
    return `<section class="panel"><div class="chart-panel"><div class="chart-heading"><div class="grow"><h3>${esc(v.label)}</h3><small class="muted">${esc(v.identifier || v.id)} · ${esc(v.unit)}</small></div>${live?ibtn('remove-chart-var', '移除观察变量', 'X', `data-id="${v.id}"`):''}</div>${history.length ? chartSvg(history, [key], 'extra-chart-' + i) : '<div class="empty"><p>此变量尚未采样或结果已过期，运行或单步后查看。</p></div>'}<div class="chart-readout" id="extra-chart-${i}-readout"></div></div></section>`;
  }).join('');
}
function chartBindingsForRun(run=currentChartRun()) {
  if(state.charts.source==='live')return state.charts.extra.filter(v=>v.projectId===project().id);
  if(Array.isArray(run.chartBindings))return run.chartBindings;
  // Legacy records did not capture chart bindings. Ordinary variable bindings
  // remain useful; a current coupling could refer to entirely different equipment.
  return state.charts.extra.filter(v=>v.projectId===run.projectId&&!isCouplingChart(v));
}
function updateExtraCharts() { const e = document.getElementById('extra-charts'); if (e) e.innerHTML = extraChartsMarkup(); }
function downloadFile(name, text, type = 'application/json') {
  const blob = text instanceof Blob ? text : new Blob([text], { type: type + ';charset=utf-8' }), url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 3000); msg('已生成导出文件。');
}
function exportData(format, id) {
  const csvCell = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  if (format === 'csv') {
    const h = currentChartRun().history; if (!h.length) throw Error('当前数据来源没有曲线可导出。');
    downloadFile('fluidnet-curves.csv', '\uFEFF' + [['time_s', 'flow_kg_s', 'a_kg_s', 'b_kg_s', 'pressure_kPa', 'temperature_C'], ...h.map(r => [r.t, r.q, r.a, r.b, r.pressure, r.temperature])].map(r => r.map(csvCell).join(',')).join('\r\n'), 'text/csv'); return;
  }
  let data, name;
  if (format === 'record' || format === 'report') { data = state.records.find(r => r.id === (id || ui.selectedRecord)) || state.records[0]; if (!data) throw Error('没有可导出的记录。'); name = data.id; }
  else if (format === 'models') { data = { format: 'fluidnet-prototype-models', schema: 1, moduleGroups: state.moduleGroups, modules: state.modules, models: state.models }; name = 'fluidnet-models'; }
  else if (format === 'variables') { data = { project: project().id, variables: projectVariables() }; name = 'fluidnet-variables'; }
  else if (format === 'messages') { data = state.messages; name = 'fluidnet-messages'; }
  else { data = clone(state); data.format = 'fluidnet-studio-prototype'; name = 'fluidnet-prototype'; }
  downloadFile(name + '.json', JSON.stringify(data, null, 2));
}
function validateImport(data) {
  const safeId = id => typeof id === 'string' && /^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id);
  if (!data || data.schema !== 1 || !Array.isArray(data.modules) || !data.modules.length || !Array.isArray(data.models)) throw Error('不是本版本的原型交换文件。');
  validateModuleGroups(data);
  if (data.modules.length > 64 || data.models.length > 500) throw Error('导入数据超出原型演示容量。');
  backfillBuiltinParams(data);
  const unique = values => new Set(values).size === values.length;
  if (!unique(data.modules.map(m => m.id)) || !unique(data.models.map(m => m.id))) throw Error('模块或型号标识重复。');
  for (const m of data.modules) {
    if (m.manifest) PARAM_DEFS[m.kind] = manifestFields(m.manifest);
    if (!safeId(m.id) || (!PARAM_DEFS[m.kind] && !m.manifest) || !isIdentifier(m.code) || typeof m.name !== 'string' || !Array.isArray(m.ports) || !Array.isArray(m.variables) || !Array.isArray(m.channels) || !m.values || m.banks?.length !== 3 || m.bankNames?.length !== 3 || !m.source || typeof m.source.runtime !== 'string' || typeof m.source.header !== 'string' || m.source.design?.length !== 3 || m.source.design.some(code => typeof code !== 'string') || (m.designSource !== undefined && typeof m.designSource !== 'string') || !m.drawing) throw Error('模块定义不完整。');
    if (m.ports.length > 24 || m.variables.length > 160 || !unique(m.ports.map(p => p.id)) || !unique(m.variables.map(v => v.id))) throw Error('端口 / 变量标识重复或数量超限。');
    if (m.ports.some(p => !safeId(p.id) || !isIdentifier(p.name) || !DOMAINS[p.domain] || !['in', 'out'].includes(p.direction) || !Number.isFinite(p.x) || !Number.isFinite(p.y))) throw Error('端口定义不合法。');
    if (m.variables.some(v => !isIdentifier(v.name) || !['int', 'double', 'int[8]', 'double[8]'].includes(v.type) || v.port && !m.ports.some(p => p.id === v.port))) throw Error('变量定义不合法。');
    if (!m.variables.some(v => v.id === 'system:form') || !m.variables.some(v => v.id === 'system:mix')) throw Error('模块缺少工质字段。');
    if (!Number.isInteger(m.precision) || m.precision < 0 || m.precision > 8) throw Error('显示精度不合法。');
    numeric(m.drawing.width, 15, 60); numeric(m.drawing.height, 15, 55);
    for (const bank of [m.values, ...m.banks]) validateBank(m, bank);
  }
  for (const item of data.models) {
    const m = data.modules.find(m => m.id === item.moduleId);
    if (!safeId(item.id) || !m || typeof item.name !== 'string' || !Array.isArray(item.versions) || !item.versions.length) throw Error('型号引用或版本数据不完整。');
    readParams(item.params, m.kind); validateModelVariables(item, m);
  }
  if (data.format === 'fluidnet-prototype-models') return;
  if (!Array.isArray(data.projects) || !data.projects.length || data.projects.length > 20 || !unique(data.projects.map(p => p.id)) || !data.bench || !data.charts || !Array.isArray(data.records) || !Array.isArray(data.messages) || !Array.isArray(data.connectors) || !Number.isInteger(data.serial)) throw Error('项目、测试或运行数据不完整。');
  for (const p of data.projects) {
    controls.normalize(p);
    if (!safeId(p.id) || typeof p.name !== 'string' || !p.solver || !Array.isArray(p.pages) || !p.pages.length || p.pages.length > 8 || !p.run?.values || !Array.isArray(p.run.history) || !Array.isArray(p.run.events) || typeof p.control !== 'string') throw Error('项目结构不合法。');
    const ids = p.pages.flatMap(pg => pg.nodes?.map(n => n.id) || []); if (!unique(ids)) throw Error('项目设备标识重复。');
    for (const pg of p.pages) {
      if (!safeId(pg.id) || !Array.isArray(pg.nodes) || pg.nodes.length > 64 || !Array.isArray(pg.edges)) throw Error('画布结构不合法。');
      for (const n of pg.nodes) { const m = p.moduleSnapshots?.[n.moduleId] || data.modules.find(m => m.id === n.moduleId); if (!safeId(n.id) || !m || !Number.isFinite(n.x) || !Number.isFinite(n.y)) throw Error('设备引用不合法。'); readParams(n.params, m.kind, '', m.manifest ? manifestFields(m.manifest) : undefined); readParams(n.draft, m.kind, '', m.manifest ? manifestFields(m.manifest) : undefined); validateInstanceVariableState(n, m); }
      for (const e of pg.edges) if (!Array.isArray(e) || e.length !== 5 || !safeId(e[0]) || !pg.nodes.some(n => n.id === e[1] && (p.moduleSnapshots?.[n.moduleId] || data.modules.find(m => m.id === n.moduleId)).ports.some(p => p.id === e[2])) || !pg.nodes.some(n => n.id === e[3] && (p.moduleSnapshots?.[n.moduleId] || data.modules.find(m => m.id === n.moduleId)).ports.some(p => p.id === e[4]))) throw Error('连接引用不存在。');
    }
    numeric(p.solver.dt, .01, 60); numeric(p.solver.duration, 1, 86400);
  }
  if (!data.projects.some(p => p.id === data.activeProject) || !data.modules.some(m => m.id === data.bench.moduleId) || !data.bench.run?.values || !Array.isArray(data.bench.run.history) || !Array.isArray(data.bench.run.events)) throw Error('当前项目或测试引用无效。');
}
function importDialog() {
  openDialog('导入原型或型号库', '读取本设计版本的 JSON，先检查完整性，再显式应用。', '<div class="file-drop"><input type="file" name="file" accept=".json,application/json" aria-label="选择原型 JSON" required></div><div id="import-preview" class="notice" style="margin-top:16px">请选择文件。导入前可以取消。</div>', () => {
    const incoming = modal.importData; if (!incoming) throw Error('请先选择并读取有效文件。');
    validateImport(incoming);
    if (incoming.format === 'fluidnet-prototype-models') {
      const conflicts = incoming.models.filter(m => state.models.some(v => v.id === m.id));
      if (conflicts.length) throw Error(`已有 ${conflicts.length} 个相同标识的型号。为避免覆盖，请使用完整原型恢复或导入不同型号。`);
      const mergedGroups = collectModuleGroups({ modules: [...state.modules, ...incoming.modules], moduleGroups: [...state.moduleGroups, ...(incoming.moduleGroups || [])] });
      state.moduleGroups = mergedGroups;
      state.modules.push(...clone(incoming.modules.filter(m => !state.modules.some(v => v.id === m.id)))); state.models.push(...clone(incoming.models));
    } else {
      backupLocalDraft(STORAGE_KEY + '-before-import');
      state = {...clone(incoming),workspaceRevision:state.workspaceRevision}; state.projects.forEach(p => { if (p.run.status === 'running') p.run.status = 'paused'; }); if (state.bench.run.status === 'running') state.bench.run.status = 'paused';
    }
    ui.floats = []; undoStack = []; redoStack = []; ui.selectedNode = ''; normalizeState(); markDirty(); navigate('home'); msg('导入已应用；点击保存原型以保留。');
  }, '应用导入');
}
function pageMap() {
  openDialog('页面导航', '所有页面使用同一份项目、模块和型号数据。', `<div class="page-map">${Object.entries(PAGE_META).map(([id, [name, glyph, desc]]) => `<button class="map-link" data-action="nav" data-route="${id}" type="button">${icon(glyph)}<span>${name}<small>${desc}</small></span></button>`).join('')}</div>`, null, '', true);
}
function chooseChartVariables(control = false) {
  const variables = projectVariables(); if (!variables.length) throw Error('先在项目中放入设备。');
  if (control) {
    const cfg = project().controlConfig;
    openDialog('控制输入与输出', '配置观察变量与可写目标。', `<div class="stack">${selectField('input', '读取变量', variables.map(v => [v.id, v.id + ' · ' + v.name]), cfg.input)}${selectField('output', '设置目标', variables.filter(v => v.writable).map(v => [v.id, v.id + ' · ' + v.name]), cfg.output)}</div>`, data => {
      cfg.input = data.input; cfg.output = data.output; markDirty(project()); render();
    }, '保存绑定');
  } else openDialog('添加观察变量', '选择设备和物理量；曲线采样与主系统的仿真时间一致。', selectField('variable', '项目变量', variables.map(v => [v.id, `${v.identifier || v.id} · ${v.device} · ${v.name} / ${v.unit}`]), variables[0].id), data => addChartVariable(data.variable), '加入曲线');
}
function handleAction(action, el) {
  if(action.startsWith('wf-')){workflows.action(action,el).catch(error=>msg(error.message,true));return;}
  if(action.startsWith('batch-')){scenarioBatches.action(action,el).catch(error=>msg(error.message,true));return;}
  if(action.startsWith('cs-')){coldStorage.action(action,el).catch(error=>msg(error.message,true));return;}
  const d = el.dataset, id = d.id;
  const changes = { 'editor-tab': 'moduleTab', 'project-filter': 'projectFilter', 'project-view': 'projectView', 'module-category': 'category', 'module-view': 'moduleView', 'model-filter': 'modelFilter', 'bench-tab': 'benchTab', 'run-filter': 'runFilter', 'settings-tab': 'settingsTab', 'connection-tab': 'connectionTab', 'node-domain': 'nodeDomain' };
  if (changes[action]) { ui[changes[action]] = d.value; saveUI(); render(); return; }
  switch (action) {
    case 'nav': closeDialog(); navigate(d.route, d.sub ? { connectionTab: d.sub } : {}); break;
    case 'page-map': pageMap(); break;
    case 'project-picker': openDialog('切换项目', '任务在后台保留，设备窗口跟随当前项目。', `<div class="stack">${state.projects.map(p => btn('open-project', esc(p.name), 'FolderOpen', `data-id="${p.id}"`)).join('')}</div>`); break;
    case 'close-dialog': closeDialog(); break;
    case 'save': saveAll(); break;
    case 'workspace-tools': workspaceTools().catch(error=>msg(error.message,true));break;
    case 'download-backup': engine.downloadBackup().then(blob=>{downloadFile('fluidnet-backup.zip',blob,'application/zip');msg('备份已生成。');}).catch(error=>msg(error.message,true));break;
    case 'choose-backup': document.getElementById('workspace-backup-file').click();break;
    case 'export-old-draft': {const original=localStorage.getItem(STORAGE_KEY+'-before-workspace');if(!original)throw Error('没有载入前的浏览器草稿备份。');downloadFile('fluidnet-browser-draft.json',original);break;}
    case 'restore-workspace-revision': {const revision=Number(d.revision);confirmChange('恢复工作区修订 '+revision,'当前草稿先备份到浏览器；恢复后生成一个新修订，已有运行档案保留。',()=>engine.restoreRevision(revision).then(receipt=>msg('已恢复为修订 '+receipt.revision)).catch(error=>msg(error.message,true)));break;}

    case 'reload-workspace':
      if(savePhase==='saving')throw Error('请等待当前保存结束。');
      confirmChange('载入服务器工作区','当前草稿将先备份到浏览器；可先导出原型保留独立文件。',()=>engine.init(true));break;
    case 'refresh-archives': engine.refreshArchives();break;
    case 'delete-archive': confirmChange('删除运行档案','将删除该运行的服务端快照和历史。',()=>engine.deleteArchive(id).then(()=>{state.records=state.records.filter(r=>r.id!==id);render();}).catch(error=>msg(error.message,true)));break;
    case 'open-archive': engine.openArchive(id).catch(error=>msg(error.message,true));break;
    case 'theme': ui.theme = ui.theme === 'dark' ? 'light' : 'dark'; saveUI(); render(); break;
    case 'open-project': closeDialog(); if (id) openProject(id); break;
    case 'start-modeling': startModeling(); break;
    case 'toggle-chart': ui.showChart = !ui.showChart; ui.pinnedChart = null; saveUI(); retainFocus(); break;
    case 'full-curves': state.charts.source = 'live'; ui.pinnedChart = null; navigate('curves'); break;
    case 'release-cursor': ui.pinnedChart = null; ui.chartCursor = null; refreshWorkbenchChart(); break;
    case 'float-dock': toggleDeviceDock(id); break;
    case 'guided-demo': state.selectedModule = 'valve'; ui.bank = 1; openEditor('valve', 'channels'); msg('从端口与通路开始，再编辑库值、保存型号并应用到项目。'); break;
    case 'new-project':
      openDialog('新建项目', '选择一份示例作为起点，或创建空白画布。', `<div class="stack">${field('name', '项目名称', '新管网项目', 'required maxlength="50"')}${selectField('template', '起始内容', [['blank', '空白画布'], ['water', '泵阀并联管网'], ['heat', '双侧换热机组'], ['tank', '水箱液位调节']], 'blank')}</div>`, data => {
        if (state.projects.length >= 20) throw Error('当前原型最多保存 20 个项目。');
        const name = data.name.trim(); if (!name) throw Error('请输入项目名称。');
        const pg = data.template === 'water' ? waterPage() : data.template === 'heat' ? heatPage() : data.template === 'tank' ? tankPage() : { id: 'main', name: '主系统', nodes: [], edges: [], zoom: 1, pan: [0, 0] };
        const p = makeProject(uid('project'), name, '', pg); state.projects.push(p); normalizeState(); markDirty(p); openProject(p.id);
      }, '创建项目'); break;
    case 'duplicate-project': {
      if(state.projects.length>=20)throw Error('最多保存 20 个项目。');
      const original=state.projects.find(p=>p.id===id);if(!original)break;
      const p=clone(original);p.id=uid('project');p.name+=' 副本';p.run=emptyRun();p.modified='本地草稿';
      const copiedCharts=clone(state.charts.extra.filter(binding=>binding.projectId===original.id));
      for(const binding of copiedCharts){binding.id=uid('chart');binding.projectId=p.id;}
      state.projects.push(p);state.charts.extra.push(...copiedCharts);markDirty(p);persistLocal();render();break;
    }
    case 'new-canvas':
    case 'rename-canvas': {
      const pg = action === 'rename-canvas' && project().pages.find(pg => pg.id === id);
      openDialog(pg ? '重命名画布' : '新增画布', project().name, field('name', '画布名称', pg?.name || `画布 ${project().pages.length + 1}`, 'required maxlength="40"'), data => {
        const name = data.name.trim(); if (!name) throw Error('请输入画布名称。'); if (!pg && project().pages.length >= 8) throw Error('当前原型每个项目最多演示 8 张画布。');
        remember(); if (pg) pg.name = name; else { const next = { id: uid('canvas'), name, nodes: [], edges: [], zoom: 1, pan: [0, 0] }; project().pages.push(next); project().activePage = next.id; }
        ui.selectedNode = ''; ui.connecting = null; markDirty(project()); render();
      }, pg ? '保存名称' : '新增画布'); break;
    }
    case 'canvas-tab': project().activePage = id; ui.selectedNode = ''; ui.selectedEdge = ''; ui.connecting = null; render(); break;
    case 'new-module-group': moduleGroupDialog(); break;
    case 'rename-module-group': moduleGroupDialog(d.value); break;
    case 'delete-module-group': removeModuleGroup(d.value); break;
    case 'move-module-group': moveModuleGroup(id); break;
    case 'new-module':
      openDialog('新建算法模块', '选择设备模板生成可运行代码；随后可配置端口、通路和参数。', `<div class="fields">${field('name', '模块名称', '自定义调节阀', 'required maxlength="40"')}${field('code', '模块标识', 'CUSTOM_VALVE', 'required pattern="[A-Za-z_][A-Za-z0-9_]*" maxlength="48"')}${selectField('base', 'Python 模板', [['template:resistance','两端口局部阻力'],['template:pump','泵／风机'],['template:heat_exchanger','双侧换热'],['template:managed_state','受管理状态'],...state.modules.filter(m=>m.runtime==='python').map(m=>[m.id,m.name])], 'programmable_valve')}${selectField('category', '所属分组', moduleGroupNames().map(name => [name, name]), ui.route === 'modules' && ui.category !== '全部模块' ? ui.category : '自定义模块')}</div>`, async data => {
        if (!isIdentifier(data.code) || state.modules.some(m => m.code === data.code)) throw Error('模块标识需合法且唯一。');
        if (state.modules.length >= 64) throw Error('已达到原型模块数量上限。');
        if (!moduleGroupNames().includes(data.category)) throw Error('请选择已有分组。');
        if (!data.name.trim()) throw Error('请输入模块名称。');
        if (!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(data.code) || state.modules.some(m=>m.id===data.code.toLowerCase())) throw Error('模块标识需以字母开头且唯一。');
        const m=data.base.startsWith('template:') ? await engine.newTemplate(data.code.toLowerCase(),data.name.trim(),data.category,data.base.slice(9)) : engine.newModule(data.code.toLowerCase(),data.name.trim(),data.category,data.base); state.modules.push(m); markDirty(m); openEditor(m.id,'code');
      }, '创建模块'); break;
    case 'edit-contract-item': editContractItem(d.section,id); break;
    case 'save-module-version': engine.saveModule(mod()); break;
    case 'create-composite': {
      const choices=activePage().nodes.filter(n=>moduleOf(n).manifest?.solver_model!=='pressure_source' && moduleOf(n).kind!=='source');
      openDialog('封装设备组','选择设备，生成带精确子版本绑定的组合草稿。',`<div class="fields">${field('id','组合标识','custom_group','required pattern="[A-Za-z][A-Za-z0-9_]*"')}${field('name','组合名称','设备组','required')}</div><div class="stack">${choices.map(n=>`<label class="check-label"><input name="node_${n.id}" type="checkbox" ${ui.selectedNode===n.id?'checked':''}>${esc(n.id+' · '+n.name)}</label>`).join('')}</div>`,async data=>{
        const ids=choices.filter(n=>data['node_'+n.id]).map(n=>n.id);
        if(!ids.length)throw Error('请选择至少一个设备。');
        if(state.modules.some(m=>m.id===data.id))throw Error('组合标识已存在。');
        const m=await engine.newComposite(project(),ids,data.id,data.name);state.modules.push(m);markDirty(m);openEditor(m.id,'contract');
      },'生成组合草稿');break;
    }
    case 'view-composite': {
      const definition=engine.manifestPayload(mod());
      const describe=(module,depth=0)=>depth>8?'超出深度限制':(module.composite?.children || []).map(child=>{
        const nested=module.composite.modules.find(m=>m.id===child.module_id && m.version===child.version);
        return `<li>${esc(child.id)} · ${esc(child.module_id)} v${child.version}<small class="mono">${esc(child.definition_hash.slice(0,16))}</small>${nested?.composite?`<ul>${describe(nested,depth+1)}</ul>`:''}</li>`;
      }).join('');
      openDialog('查看组合展开',definition.name,`<ul>${describe(definition)}</ul><pre class="code-preview">${esc(JSON.stringify(definition.composite.external_ports,null,2))}</pre>`);break;
    }
    case 'module-error-line': {
      openEditor(mod().id,'code');
      const editor=document.getElementById(d.file==='design.py'?'module-code-design':'module-code'), line=Math.max(1,Number(d.line));
      if(editor){const lines=editor.value.split('\n'), start=lines.slice(0,line-1).reduce((sum,text)=>sum+text.length+1,0);editor.focus();editor.setSelectionRange(start,start+(lines[line-1]?.length || 0));editor.scrollTop=(line-1)*parseFloat(getComputedStyle(editor).lineHeight);}
      break;
    }
    case 'export-module-replay': downloadFile(`${mod().id}-replay.json`,JSON.stringify(mod().authoringReplay,null,2)); break;
    case 'configure-module-tests': configureAuthoringSuite(mod()); break;
    case 'module-test-suite': runAuthoringSuite(mod()); break;
    case 'cancel-module-suite': ui.moduleSuiteAbort?.abort(); break;
    case 'validate-module-contract': engine.checkModule(mod(),true); break;
    case 'module-versions': engine.versions(mod()); break;
    case 'load-module-version': engine.loadVersion(mod(),Number(d.version)); break;
    case 'edit-module': openEditor(id || state.selectedModule, d.tab || 'drawing'); break;
    case 'module-doc': openModuleDoc(id); break;
    case 'insert-module': navigate('workbench'); newInstance(id); break;
    case 'place-module': ui.placing = ui.placing === id ? null : id; ui.connecting = null; render(); break;
    case 'insert-defaults': remember(); {
      const w = waterPage(), used = project().pages.filter(pg => pg !== activePage()).flatMap(pg => pg.nodes.map(n => n.id));
      const mapping = Object.fromEntries(w.nodes.map(n => [n.id, used.includes(n.id) ? uid(n.id) : n.id]));
      w.nodes.forEach(n => n.id = mapping[n.id]); w.edges = w.edges.map(e => [uid('edge'), mapping[e[1]], e[2], mapping[e[3]], e[4]]);
      activePage().nodes = w.nodes; activePage().edges = w.edges;
    } markDirty(project()); render(); break;
    case 'open-device': openDevice(id); break;
    case 'apply-instance': applyInstanceDialog(instance(id)); break;
    case 'apply-instance-bank': applyInstanceBank(instance(id), Number(d.bank)); break;
    case 'capture-instance-bank': captureInstanceBank(instance(id), Number(d.bank)); break;
    case 'instance-array': editInstanceArray(instance(id), d.instanceValue, Number(d.instanceSource)); break;
    case 'copy-device': copyDevice(id); break;
    case 'rotate-device': rotateDevice(id, d.direction === '-1' ? -1 : 1); break;
    case 'device-variables': openDeviceVariables(id, d.variable); break;
    case 'choose-device-model': chooseDeviceModel(id); break;
    case 'device-definition': openDeviceDefinition(id, d.variable); break;
    case 'return-device': returnToDevice(); break;
    case 'observe-instance-variable': observeInstanceVariable(id, d.variable); break;
    case 'save-instance-model': saveInstanceModel(id); break;
    case 'delete-node': deleteNode(id || ui.selectedNode); break;
    case 'delete-edge': deleteEdge(id || ui.selectedEdge); break;
    case 'undo': undo(); break;
    case 'redo': undo(true); break;
    case 'select-mode': ui.canvasMode = 'select'; ui.connecting = null; ui.placing = null; render(); break;
    case 'connect-mode': ui.canvasMode = 'connect'; ui.placing = null; msg('点击两个空闲端口建立连接，也可以拖动连线。'); break;
    case 'toggle-library': ui.showLibrary = !ui.showLibrary; saveUI(); retainFocus(); break;
    case 'zoom-in': activePage().zoom = clamp(activePage().zoom * 1.2, .35, 3); render(); break;
    case 'zoom-out': activePage().zoom = clamp(activePage().zoom / 1.2, .35, 3); render(); break;
    case 'fit': fitNetwork(); render(); break;
    case 'grid': ui.pageGrid = !ui.pageGrid; saveUI(); render(); break;
    case 'validate': engine.validate(); break;
    case 'locate-issue': closeDialog(); if (d.page) project().activePage = d.page; navigate('workbench'); if (id) openDevice(id); break;
    case 'select-picture': ui.editorPort = 'picture'; render(); break;
    case 'draw-center': for (const p of mod().ports) { p.x = p.direction === 'in' ? 20 : 80; p.y = 30 + mod().ports.filter(x => x.direction === p.direction).indexOf(p) * 25; } markDirty(mod()); render(); break;
    case 'edit-drawing-label': ui.editorPort = 'picture'; render(); root.querySelector('[data-drawing-field="label"]')?.focus(); break;
    case 'add-port': {
      const m = mod(); if (m.ports.length >= 24 || m.variables.length + 7 > 160) throw Error('达到本原型的端口或变量容量。');
      const prefix = PORT_PREFIX[d.domain][d.direction === 'in' ? 0 : 1];
      let i = 0; while (m.ports.some(p => p.name === prefix + i)) i++;
      const p = port(uid('port'), prefix + i, DOMAINS[d.domain].label + (d.direction === 'in' ? '输入' : '输出'), d.direction, d.domain, d.direction === 'in' ? 20 : 80, 20 + i % 3 * 25);
      m.ports.push(p); refreshPortVariables(m); ui.editorPort = p.id; markDirty(m); render(); break;
    }
    case 'delete-port': {
      const m = mod();
      if (m.channels.some(c => c.input === id || c.output === id)) throw Error('先解除此端口的内部通路绑定，再删除。');
      if (state.projects.some(p => p.pages.some(pg => pg.edges.some(e => [1, 3].some(i => pg.nodes.find(n => n.id === e[i])?.moduleId === m.id && e[i + 1] === id))))) throw Error('项目中仍有连接使用此端口，请先断开连接。');
      m.ports = m.ports.filter(p => p.id !== id); refreshPortVariables(m); ui.editorPort = ''; markDirty(m); render(); break;
    }
    case 'add-channel': {
      const m = mod(), used = m.channels.filter(c => c.enabled).flatMap(c => [c.input, c.output]);
      m.channels.push({ id: uid('channel'), name: '通路 ' + m.channels.length, input: m.ports.find(p => p.direction === 'in' && !used.includes(p.id))?.id || '', output: m.ports.find(p => p.direction === 'out' && !used.includes(p.id))?.id || '', enabled: true, kind: 'resistance' }); markDirty(m); render(); break;
    }
    case 'delete-channel': mod().channels = mod().channels.filter(c => c.id !== id); markDirty(mod()); render(); break;
    case 'check-channels': {
      const errors = checkChannels(mod()), target = document.getElementById('channel-feedback');
      target.innerHTML = `<div class="notice ${errors.length ? 'error' : 'good'}" role="${errors.length ? 'alert' : 'status'}">${icon(errors.length ? 'Info' : 'CheckCircle2')}<span>${errors.length ? errors.map(esc).join('<br>') : '通路检查通过：端口存在、领域一致，且没有重复绑定。'}</span></div>`; break;
    }
    case 'new-variable':
      openDialog('新增自定义变量', '变量标识用于代码、参数方案与曲线。', `<div class="fields">${field('name', '变量标识', 'CUSTOM_VALUE', 'required maxlength="48"')}${field('label', '中文名称', '自定义参数', 'required maxlength="60"')}${selectField('type', '数据类型', ['double', 'int', 'double[8]', 'int[8]'].map(t => [t, t]), 'double')}${field('unit', '单位', '—', 'maxlength="24"')}</div>`, data => {
        const m = mod(); if (!isIdentifier(data.name) || m.variables.some(v => v.name === data.name)) throw Error('变量标识需合法且唯一。');
        if (m.variables.length >= 160) throw Error('变量数量达到原型上限。');
        const value = data.type.endsWith('[8]') ? Array(8).fill(0) : 0, v = { id: uid('var'), name: data.name, label: data.label, unit: data.unit, type: data.type, origin: 'custom', port: '', note: data.label, display: true, writable: true, value };
        m.variables.push(v); [m.values, ...m.banks].forEach(x => x[v.id] = clone(value)); markDirty(m); render();
      }, '新增变量'); break;
    case 'delete-variable': mod().variables = mod().variables.filter(v => v.id !== id); [mod().values, ...mod().banks].forEach(x => delete x[id]); if (ui.arrayVar === id) ui.arrayVar = 'system:form'; markDirty(mod()); render(); break;
    case 'array-select': ui.arrayVar = id; ui.bank = Number(d.bank); render(); break;
    case 'bank-select': ui.bank = Number(d.value); saveUI(); render(); break;
    case 'apply-bank': showBankApplication(); break;
    case 'capture-bank': confirmChange('将当前值存入此库', `用模块当前值替换库值 ${ui.bank + 1} · ${mod().bankNames[ui.bank]}。`, () => { mod().banks[ui.bank] = clone(mod().values); markDirty(mod()); render(); msg('当前值已存入所选库值。'); }, '存入库值'); break;
    case 'normalize-mixture': {
      const bank = mod().banks[ui.bank], form = bank['system:form'], mix = bank['system:mix'];
      mix.forEach((v, i) => mix[i] = form[i] ? Math.max(0, Number(v) || 0) : 0); const sum = mix.reduce((a, b) => a + b, 0);
      if (!form.some(Boolean)) throw Error('请先选择工质。'); if (!sum) form.forEach((v, i) => mix[i] = v ? 1 / form.filter(Boolean).length : 0); else mix.forEach((v, i) => mix[i] = v / sum);
      markDirty(mod()); render(); break;
    }
    case 'new-model': createModelDialog(); break;
    case 'edit-model': createModelDialog(id); break;
    case 'select-model': state.selectedModel = id; navigate('models'); break;
    case 'focus-model': state.selectedModel = id; render(); break;
    case 'archive-model': model(id).archived = !model(id).archived; markDirty(); render(); break;
    case 'insert-model': { const item = model(id); if (item.archived) throw Error('先恢复已归档型号，再插入。'); navigate('workbench'); const n = newInstance(item.moduleId, null, item); openDevice(n.id); break; }
    case 'apply-model-to-instance': {
      const item = model(id), candidates = project().pages.flatMap(pg => pg.nodes).filter(n => n.moduleId === item.moduleId);
      if (!candidates.length) throw Error('当前项目没有兼容设备，可先插入此型号。');
      openDialog('选择应用设备', `${item.name} · v${item.version}。所选型号先进入设备草稿。`, selectField('node', '目标设备', candidates.map(n => [n.id, `${n.id} · ${n.name}`]), candidates[0].id), data => {
        const n = instance(data.node); stageModel(n, id); project().activePage = project().pages.find(pg => pg.nodes.includes(n)).id; navigate('workbench'); openDevice(n.id); msg('型号已进入草稿，预览并应用后生效。');
      }, '进入设备草稿'); break;
    }
    case 'model-version': { const item = model(id), old = item.versions.find(v => v.version === Number(d.version)); openDialog(`型号版本对照 · v${old.version} → v${item.version}`, item.name, diffMarkup(Object.keys(item.params).map(k => [k, old.params[k], item.params[k]])), null, '', true); break; }
    case 'check-code': previewCode(d.kind); break;
    case 'compile-preview': previewCode('runtime', true); break;
    case 'preview-design': runDesign(d.index === undefined ? ui.bank : Number(d.index)); break;
    case 'insert-code-variable': {
      const area = root.querySelector(`textarea[data-code-kind="${ui.codeKind}"]`), variable = root.querySelector('[data-code-variable]')?.value;
      if (!area || !mod().variables.some(v => v.name === variable)) break;
      area.setRangeText(variable, area.selectionStart, area.selectionEnd, 'end'); area.dispatchEvent(new Event('input', { bubbles: true })); area.focus(); break;
    }
    case 'module-example': createModuleExample(id); break;
    case 'test-module': setBench(id); break;
    case 'run-bench': commandRun('bench', d.command); break;
    case 'record-bench': recordRun('bench'); break;
    case 'run-project': commandRun('project', d.command); break;
    case 'stop-task': commandRun('project', 'stop', id); break;
    case 'record-project': recordRun('project'); break;
    case 'tasks': ui.taskDrawer = !ui.taskDrawer; renderFloats(); break;
    case 'select-record': ui.selectedRecord = id; render(); break;
    case 'record-curves': state.charts.source = id; navigate('curves'); break;
    case 'toggle-series': ui.pinnedChart = null; state.charts.series[d.value] = !state.charts.series[d.value]; markDirty(); render(); break;
    case 'add-chart-variable': chooseChartVariables(); break;
    case 'choose-control-vars': chooseChartVariables(true); break;
    case 'add-specific-curve': addChartVariable(id, d.label); break;
    case 'device-curve': {
      const v = projectVariables().find(v => v.nodeId === id && v.origin === 'port' && v.variableId.endsWith(':FLOW'));
      if (!v) throw Error('此设备暂未提供出口流量采样。');
      addChartVariable(v.id); break;
    }
    case 'remove-chart-var': state.charts.extra = state.charts.extra.filter(v => v.id !== id || v.projectId !== project().id); markDirty(); render(); break;
    case 'add-control-program': {
      const p=project(),programs=controls.normalize(p);let suffix=1;
      while(programs.some(program=>program.id==='control_'+suffix))suffix++;
      openDialog('新建控制脚本','脚本各自保存输入输出、采样周期和状态。',field('id','脚本标识','control_'+suffix,'required maxlength="81"')+field('name','脚本名称','控制程序 '+suffix,'required maxlength="80"'),data=>{
        controls.add(p,data.id.trim(),data.name.trim());ui.controlOutput='控制脚本尚未预览。';markDirty(p);render();
      },'新建');break;
    }
    case 'remove-control-program': {const p=project(),id=d.id;confirmChange('删除控制脚本',`删除 ${id}；当前运行仍使用启动时的脚本快照。`,()=>{controls.remove(p,id);ui.controlOutput='控制脚本尚未预览。';markDirty(p);render();});break;}
    case 'control-template': confirmChange('载入 Python 控制示例','替换所选脚本、输入和输出声明，启用状态保持关闭；示例要求存在 V1 阀门。',()=>{const p=project();controls.update(p,{source:controlTemplate(),language:'python',enabled:false,inputs:['V1.mass_flow_kg_s'],outputs:['V1.param.opening_ratio']});markDirty(p);render();});break;
    case 'preview-control': {
      const owner=project(),scriptId=owner.selectedControlId;
      ui.controlOutput='正在执行一个控制周期…';document.getElementById('control-output').textContent=ui.controlOutput;
      engine.previewControl(owner).then(result=>{if(project()!==owner||owner.selectedControlId!==scriptId)return;ui.controlOutput='预览成功（未应用到项目）\n'+JSON.stringify(result,null,2);const el=document.getElementById('control-output');if(el)el.textContent=ui.controlOutput;}).catch(error=>{if(project()!==owner||owner.selectedControlId!==scriptId)return;ui.controlOutput='预览失败：'+error.message;const el=document.getElementById('control-output');if(el)el.textContent=ui.controlOutput;msg(error.message,true);});break;
    }

    case 'api-example': ui.apiKind = d.value; apiPreview(d.value); root.querySelectorAll('[data-action="api-example"]').forEach(e => e.classList.toggle('active', e.dataset.value === d.value)); break;
    case 'api-preview': apiSend().catch(error => msg(error.message, true)); break;
    case 'copy-var': if (navigator.clipboard?.writeText) navigator.clipboard.writeText(d.value).then(() => msg('变量标识已复制。')).catch(() => openDialog('变量标识', '可选中复制。', field('identifier', '变量标识', d.value, 'readonly'))); else openDialog('变量标识', '可选中复制。', field('identifier', '变量标识', d.value, 'readonly')); break;
    case 'add-connector': { const c = { id: uid('serial'), name: '串口连接 ' + state.connectors.length, kind: 'serial', port: 'COM3', baud: '115200', connected: false }; state.connectors.push(c); ui.selectedConnector = c.id; markDirty(); render(); break; }
    case 'select-connector': ui.selectedConnector = id; render(); break;
    case 'connect-demo': { const c = state.connectors.find(c => c.id === id); c.connected = !c.connected; log(`${c.name}：${c.connected ? '模拟连接成功' : '已断开演示'}`, 'SERIAL'); markDirty(); render(); break; }
    case 'serial-send': {
      const c = state.connectors.find(c => c.id === id); if (!c?.connected) throw Error('先启动连接演示。');
      const text = document.getElementById('serial-message').value.slice(0, 500); log(`${c.name} TX ${text}`, 'SERIAL');
      document.getElementById('serial-output').textContent = `TX > ${text}\nRX < DEMO_ACK（示例回显）\n未访问串口硬件。`; markDirty(); break;
    }
    case 'add-binding':
      openDialog('添加变量映射', '外部写入只能绑定到可设置的参数。', `<div class="stack">${field('external', '外部字段', 'Device.Value', 'required maxlength="80"')}${selectField('variable', '项目变量', projectVariables().map(v => [v.id, v.id + ' · ' + v.name]), projectVariables()[0]?.id)}${selectField('direction', '数据方向', [['read', '项目 → 外部'], ['write', '外部 → 项目']], 'read')}</div>`, data => {
        const v = projectVariables().find(v => v.id === data.variable); if (!v || data.direction === 'write' && !v.writable) throw Error('目标变量不存在或不可写。');
        const bindings = bindingsForProject(); if (bindings.some(b => b.external === data.external)) throw Error('此外部字段已绑定。'); bindings.push({ ...data, unit: v.unit }); markDirty(project()); render();
      }, '添加映射'); break;
    case 'demo-message': log('演示消息：变量快照已更新，原型接口没有外部连接。', 'DEMO'); markDirty(); render(); break;
    case 'export': exportData(d.format, id); break;
    case 'import': importDialog(); break;
    case 'reset-windows': state.windowPositions = {}; ui.floats.forEach(f => { delete f.x; delete f.y; delete f.restore; f.docked = false; f.minimized = false; f.w = 440; f.h = 520; }); markDirty(); render(); msg('窗口位置已恢复。'); break;
    case 'reset-prototype': confirmChange('恢复内置示例', '替换当前原型草稿。可先取消并导出编辑内容。', () => { backupLocalDraft(STORAGE_KEY + '-before-reset'); state = initialState(); normalizeState(); ui.floats = []; ui.selectedNode = ''; undoStack = []; redoStack = []; state.dirty = true; navigate('home'); msg('已恢复示例；保存后更新浏览器记录。'); }, '恢复示例'); break;
    case 'float-close': { const f = ui.floats.find(f => f.id === id); rememberWindow(f); ui.floats = ui.floats.filter(f => f.id !== id); renderFloats(); break; }
    case 'float-tab': {
      const f = ui.floats.find(f => f.id === id); setDeviceTab(f, d.value);
      renderFloats(); break;
    }
    case 'float-pin': { const f = ui.floats.find(f => f.id === id); f.pinned = !f.pinned; rememberWindow(f); renderFloats(); break; }
    case 'float-min': { const f = ui.floats.find(f => f.id === id); f.minimized = !f.minimized; renderFloats(); break; }
    case 'float-max': { const f = ui.floats.find(f => f.id === id), r = page.getBoundingClientRect(); f.docked = false; rememberWindow(f); if (f.restore) { Object.assign(f, f.restore); delete f.restore; } else { f.restore = { x: f.x, y: f.y, w: f.w, h: f.h }; Object.assign(f, { x: r.left + 8, y: r.top + 8, w: r.width - 16, h: r.height - 16 }); } renderFloats(); break; }
    // Handled by their own document listeners (PID panel, circuit fluids).
    case 'pid-example': case 'add-pid': case 'remove-pid': case 'add-circuit-fluid': case 'remove-circuit-fluid': break;
    default: throw Error(`尚未识别此操作：${action}`);
  }
}
function parseCurveDraft(text) {
  let parsed;
  try { parsed = JSON.parse(text); }
  catch { throw Error('曲线参数必须是 JSON 点对数组，例如 [[0, 20], [1, 10]]'); }
  if (!Array.isArray(parsed) || !parsed.length || !parsed.every(row => Array.isArray(row) && row.length === 2
      && row.every(v => typeof v === 'number' && Number.isFinite(v)))) throw Error('曲线参数必须是数值点对数组，例如 [[0, 20], [1, 10]]');
  return parsed;
}
// One draft path for every parameter type: the applied value only changes through 预览并应用.
function setInstanceParamDraft(el) {
  const d = el.dataset, n = instance(d.id), type = d.paramType || 'number';
  const value = type === 'boolean' ? el.checked
    : type === 'text' ? el.value
    : type === 'curve' ? parseCurveDraft(el.value)
    : el.value === '' ? '' : Number(el.value);
  n.draft[d.instanceParam] = value;
  el.closest('.parameter-row')?.classList.toggle('edited', !sameValue(value, n.params[d.instanceParam]));
  markDirty(project());
}
function setBenchParam(el) {
  if (state.bench.run.status === 'running') throw Error('暂停后编辑测试参数。');
  const d = el.dataset, type = d.paramType || 'number';
  let value;
  if (type === 'boolean') value = el.checked;
  else if (type === 'text') value = el.value;
  else if (type === 'curve') value = parseCurveDraft(el.value);
  else { const spec = (PARAM_DEFS[mod(state.bench.moduleId).kind] || []).find(f => f[0] === d.benchParam); value = numeric(el.value, spec[3], spec[4]); }
  state.bench.params[d.benchParam] = value;
  markDirty();
}
function handleInput(el) {
  const d = el.dataset, value = el.value;
  if (d.instanceSearch) {
    const f = ui.floats.find(f => f.id === d.instanceSearch); variableWindowState(f).search = value;
    const table = root.querySelector(`[data-instance-table="${f.id}"]`); table.innerHTML = instanceVariableRows(f, instance(f.id)); return;
  }
  if (d.instanceValue) { updateInstanceVariableInput(el); return; }
  if (d.filter) {
    if (d.filter === 'canvasModuleSearch') document.getElementById('canvas-library-list').innerHTML = libraryMarkup(value);
    else { ui[d.filter] = value; retainFocus(); }
    return;
  }
  if (d.benchParam) { if (d.paramType !== 'curve') setBenchParam(el); return; }
  if ('moduleContract' in d) { mod().contractDraft=value; markDirty(mod()); return; }
  if ('releaseNotes' in d) { mod().releaseNotes=value; markDirty(mod()); return; }
  if (d.codeKind) {
    if (d.codeKind === 'design-source') mod().designSource = value;
    else if (d.codeKind === 'design') mod().source.design[Number(d.designIndex)] = value; else mod().source[d.codeKind] = value;
    const lines = el.previousElementSibling;
    if (lines) { lines.textContent = value.split('\n').map((_, i) => i + 1).join('\n'); lines.scrollTop = el.scrollTop; }
    markDirty(mod()); return;
  }
  if ('controlCode' in d) { controls.update(project(),{source:value}); el.previousElementSibling.textContent = value.split('\n').map((_, i) => i + 1).join('\n'); markDirty(project()); return; }
  if ('controlInputs' in d || 'controlOutputs' in d) {controls.update(project(),{['controlInputs' in d?'inputs':'outputs']:controls.names(value)});markDirty(project());return;}
  if ('controlName' in d) { controls.update(project(),{name:value}); markDirty(project()); return; }
  if (d.varNote) { mod().variables.find(v => v.id === d.varNote).note = value; markDirty(mod()); return; }
  if (d.instanceParam) {
    if (d.paramType === 'curve') return;  // curve drafts validate on change, not on every keystroke
    const n = instance(d.id); setInstanceParamDraft(el);
    if ((d.paramType || 'number') === 'number') el.closest('.parameter-row')?.querySelectorAll('input[type="range"],input[type="number"]').forEach(other => { if (other !== el) other.value = el.value; });
    const float = el.closest('.floater'), pending = float?.querySelector('[data-pending-for]');
    if (pending) { pending.textContent = `${pendingCount(n)} 项待应用`; pending.className = `badge ${pendingCount(n) ? 'warn' : 'good'}`; }
    const apply = float?.querySelector('[data-action="apply-instance"]'); if (apply) apply.disabled = !pendingCount(n);
    return;
  }
  if (d.instanceName) { const n = instance(d.instanceName); if (value.trim()) n.name = value; markDirty(project()); return; }
  if (d.valueId) {
    const v = mod().variables.find(v => v.id === d.valueId); if (Number(d.bank) < 0 || !v.writable) return;
    mod().banks[Number(d.bank)][d.valueId] = value === '' ? '' : Number(value); el.closest('td')?.classList.add('edited'); markDirty(mod()); return;
  }
  if ('bankName' in d) { mod().bankNames[Number(d.bankName)] = value; markDirty(mod()); return; }
  if (d.projectField && ['name', 'description'].includes(d.projectField)) { if (d.projectField !== 'name' || value.trim()) project()[d.projectField] = value; markDirty(project()); }
}
function handleChange(el) {
  const d = el.dataset, value = el.value; let redraw = true;
  if (d.deviceModelSource) { document.getElementById('device-model-preview').innerHTML = instanceModelPreview(instance(d.deviceModelSource), value); return; }
  if ('workbenchChart' in d) { ui.workbenchChart = value; ui.pinnedChart = null; saveUI(); retainFocus(); return; }
  if (el.type === 'file' && modal && el.name === 'file') {
    const file = el.files[0], current = modal; if (!file) return;
    if (file.size > 5_000_000) throw Error('请使用小于 5 MB 的原型 JSON。');
    file.text().then(text => {
      if (modal !== current) return;
      try { const data = JSON.parse(text); validateImport(data); current.importData = data; document.getElementById('import-preview').textContent = `${data.projects?.length || 0} 个项目 · ${data.modules.length} 个模块 · ${data.models.length} 个型号。确认后${data.format === 'fluidnet-prototype-models' ? '合并型号库' : '替换当前原型草稿'}。`; }
      catch (err) { current.importData = null; document.getElementById('import-preview').textContent = '检查失败：' + err.message; document.getElementById('import-preview').className = 'notice error'; }
    }); return;
  }
  if (d.instanceSourceSelect || d.instanceGroup || d.instanceToggle) {
    const f = ui.floats.find(f => f.id === (d.instanceSourceSelect || d.instanceGroup || d.id)), config = variableWindowState(f);
    if (d.instanceSourceSelect) config.source = Number(value);
    else if (d.instanceGroup) config.group = value;
    else config[d.instanceToggle] = el.checked;
    retainFocus(renderFloats); return;
  }
  if (d.uiToggle) { ui[d.uiToggle] = el.checked; saveUI(); }
  else if ('themeSelect' in d) { ui.theme = value; saveUI(); }
  else if (d.moduleField) { mod()[d.moduleField] = d.moduleField === 'precision' ? numeric(value, 0, 8, true) : value; markDirty(mod()); }
  else if (d.drawingField) { mod().drawing[d.drawingField] = ['width', 'height'].includes(d.drawingField) ? numeric(value, 15, d.drawingField === 'width' ? 60 : 55) : value; markDirty(mod()); }
  else if (d.portField) {
    const m = mod(), p = m.ports.find(p => p.id === d.id);
    if (d.portField === 'name' && (!isIdentifier(value) || m.ports.some(x => x.id !== p.id && x.name === value))) throw Error('端口标识需合法且唯一。');
    p[d.portField] = ['x', 'y'].includes(d.portField) ? numeric(value, d.portField === 'x' ? 5 : 10, d.portField === 'x' ? 95 : 85) : value;
    refreshPortVariables(m); markDirty(m);
  }
  else if (d.channelField) { const c = mod().channels.find(c => c.id === d.channelId); c[d.channelField] = el.type === 'checkbox' ? el.checked : value; markDirty(mod()); }
  else if (d.varDisplay) { mod().variables.find(v => v.id === d.varDisplay).display = el.checked; markDirty(mod()); redraw = false; }
  else if ('arrayVar' in d) ui.arrayVar = value;
  else if ('arrayIndex' in d) { const v = mod().variables.find(v => v.id === d.id); mod().banks[ui.bank][d.id][Number(d.arrayIndex)] = numeric(value, -1e12, 1e12, v.type.startsWith('int')); markDirty(mod()); }
  else if ('mixtureIndex' in d) { mod().banks[ui.bank]['system:mix'][Number(d.mixtureIndex)] = numeric(value, 0, 1); markDirty(mod()); }
  else if (d.fluidId) {
    const bank = mod().banks[ui.bank], form = bank['system:form'], mix = bank['system:mix'], fid = Number(d.fluidId), old = form.indexOf(fid);
    if (el.checked && old < 0) { const i = form.indexOf(0); if (i < 0) throw Error('最多选择 8 个工质组分。'); form[i] = fid; mix[i] = form.filter(Boolean).length === 1 ? 1 : 0; }
    else if (!el.checked && old >= 0) { if (form.filter(Boolean).length === 1) { el.checked = true; throw Error('至少保留一种工质。'); } form[old] = 0; mix[old] = 0; }
    markDirty(mod());
  }
  else if ('codeTarget' in d) { selectCodeTarget(value); return; }
  else if ('codeVariable' in d) { ui.codeVariable = value; return; }
  else if ('designSelect' in d) {
    ui.designIndex = Number(value); selectCodeTarget('design');
    root.querySelector('[data-code-pane="design"]').outerHTML = renderCodePane('design');
    root.querySelector('[data-design-select]').focus({ preventScroll: true }); return;
  }
  else if (d.instanceModel) {
    const n = instance(d.instanceModel); if (value) stageModel(n, value); else { n.draftModelId = null; n.draftModelVersion = null; markDirty(project()); }
  }
  else if (d.instanceSwitch) { const n = instance(d.id), f = paramDefs(n).find(f => f[0] === d.instanceSwitch); n.draft[f[0]] = el.checked ? f[4] : f[3]; markDirty(project()); }
  else if (d.instanceParam) { setInstanceParamDraft(el); redraw = false; }  // a blur-driven change must not replace the float DOM mid-click
  else if ('benchModule' in d) { setBench(value); return; }
  else if (d.benchParam) { setBenchParam(el); }
  else if (d.benchBoundary) { if (state.bench.run.status === 'running') throw Error('暂停后编辑测试边界。'); state.bench.boundary[d.benchBoundary] = numeric(value, d.benchBoundary === 'temperature' ? -273 : .001, 100000); markDirty(); }
  else if ('benchStep' in d) { state.bench.run.step = numeric(value, .01, 10); markDirty(); }
  else if ('chartSource' in d) { ui.pinnedChart = null; state.charts.source = value; markDirty(); }
  else if ('chartCompare' in d) { state.charts.compare = el.checked; markDirty(); }
  else if ('chartRange' in d) { state.charts.range = value; markDirty(); if (value === 'all') engine.loadOverview(project()); }
  else if ('solverContinuous' in d) { project().solver.continuous = el.checked; markDirty(project()); }
  else if (d.projectField) { project()[d.projectField] = value; markDirty(project()); }
  else if (d.solverField) {
    const bounds = { duration: [1, 86400], dt: [.01, 60], massAtol: [1e-12, 1], pressureAtol: [1e-12, 100000], maxIter: [5, 500] };
    project().solver[d.solverField] = (d.solverField === 'mode' || d.solverField === 'hydraulicMethod') ? value : numeric(value, ...bounds[d.solverField], d.solverField === 'maxIter'); markDirty(project());
  }
  else if ('controlProgram' in d) { controls.select(project(),value);ui.controlOutput='控制脚本尚未预览。';persistLocal(); }
  else if ('controlEnabled' in d) { controls.update(project(),{enabled:el.checked});markDirty(project()); }
  else if ('controlLanguage' in d) {controls.update(project(),{language:value,enabled:false});markDirty(project());}
  else if (d.controlSetting) { controls.update(project(),{sample_s:numeric(value,1,60000,true)/1000});markDirty(project());redraw=false; }
  else if ('controlTimeout' in d) { controls.update(project(),{timeout_s:numeric(value,.1,30)});markDirty(project());redraw=false; }
  else if (d.connectorField) { state.connectors.find(c => c.id === d.connectorId)[d.connectorField] = value; markDirty(); }
  else if ('bindingIndex' in d) { const b = bindingsForProject()[Number(d.bindingIndex)], v = projectVariables().find(v => v.id === value); if (b.direction === 'write' && !v.writable) throw Error('外部写入只能绑定可设置参数。'); b.variable = v.id; b.unit = v.unit; markDirty(project()); }
  else redraw = false;
  if (d.benchParam || d.benchBoundary || 'benchStep' in d) { const step=state.bench.run.step; state.bench.run={...emptyRun('bench'),step}; }
  if (redraw) retainFocus();
}
function svgPoint(svg, e) { return new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse()); }
function setPointer(e, data) { pointer = { ...data, startX: e.clientX, startY: e.clientY, pointerId: e.pointerId, moved: false }; }
root.addEventListener('pointerdown', e => {
  if (e.button !== 0 || modal) return;
  const target = e.target, resize = target.closest('[data-float-resize]'), move = target.closest('[data-float-move]'), draw = target.closest('[data-draw-id]'), portEl = target.closest('[data-port-node]'), node = target.closest('[data-node]');
  if (resize || move && !target.closest('button,input,select')) {
    const f = ui.floats.find(f => f.id === (resize ? resize.dataset.floatResize : move.dataset.floatMove)); if (isDocked(f)) return; ui.frontId = f.id; f.order = ++ui.floatSerial;
    setPointer(e, { kind: resize ? 'resize' : 'window', id: f.id, original: { x: f.x, y: f.y, w: f.w, h: f.h } }); e.preventDefault(); return;
  }
  if (draw && draw.dataset.drawId !== 'picture') {
    const p = mod().ports.find(p => p.id === draw.dataset.drawId); ui.editorPort = p.id;
    setPointer(e, { kind: 'draw-port', id: p.id, original: { x: p.x, y: p.y }, origin: svgPoint(document.getElementById('module-drawing'), e) }); e.preventDefault(); return;
  }
  if (portEl) { setPointer(e, { kind: 'port', nodeId: portEl.dataset.portNode, portId: portEl.dataset.portId }); e.preventDefault(); return; }
  if (node && !target.closest('[data-quick-node]')) { const n = instance(node.dataset.node); ui.selectedNode = n.id; setPointer(e, { kind: 'node', id: n.id, original: { x: n.x, y: n.y }, origin: svgPoint(document.getElementById('network'), e) }); e.preventDefault(); return; }
  if (target.closest('#network') && !target.closest('[data-edge]') && !ui.placing) setPointer(e, { kind: 'pan', original: [...activePage().pan], origin: svgPoint(document.getElementById('network'), e), matrix: document.getElementById('network').getScreenCTM().inverse() });
});
root.addEventListener('pointermove', e => {
  if (!pointer || pointer.pointerId !== e.pointerId) { chartHover(e); return; }
  const dx = e.clientX - pointer.startX, dy = e.clientY - pointer.startY;
  if (!pointer.moved && Math.hypot(dx, dy) > 4) { pointer.moved = true; root.setPointerCapture(e.pointerId); if (pointer.kind === 'node') remember(); }
  if (!pointer.moved) return;
  if (pointer.kind === 'window' || pointer.kind === 'resize') {
    const f = ui.floats.find(f => f.id === pointer.id);
    if (pointer.kind === 'window') { f.x = pointer.original.x + dx; f.y = pointer.original.y + dy; } else { f.w = pointer.original.w + dx; f.h = pointer.original.h + dy; }
    windowBounds(f); const el = root.querySelector(`[data-float-id="${f.id}"]`); Object.assign(el.style, { left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: (f.minimized ? 46 : f.h) + 'px' });
  } else if (pointer.kind === 'node') {
    const svg = document.getElementById('network'), p = svgPoint(svg, e), n = instance(pointer.id);
    n.x = Math.round(pointer.original.x + p.x - pointer.origin.x); n.y = Math.round(pointer.original.y + p.y - pointer.origin.y); svg.innerHTML = networkMarkup(activePage());
  } else if (pointer.kind === 'pan') {
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(pointer.matrix); activePage().pan = [pointer.original[0] + p.x - pointer.origin.x, pointer.original[1] + p.y - pointer.origin.y];
    const pg = activePage(); document.getElementById('network').setAttribute('viewBox', networkViewBox(pg));
  } else if (pointer.kind === 'draw-port') {
    const svg = document.getElementById('module-drawing'), p = svgPoint(svg, e), port = mod().ports.find(p => p.id === pointer.id);
    port.x = Math.round(clamp(pointer.original.x + (p.x - pointer.origin.x) / 7.2, 5, 95)); port.y = Math.round(clamp(pointer.original.y + (p.y - pointer.origin.y) / 4.3, 10, 85)); svg.innerHTML = drawingSVG(mod());
  }
});
root.addEventListener('pointerup', e => {
  if (!pointer) return; const completed = pointer; pointer = null;
  try { root.releasePointerCapture(e.pointerId); } catch {}
  if (!completed.moved) return;
  ui.ignoreClickUntil = Date.now() + 100;
  if (completed.kind === 'port') {
    const hit = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-port-node]');
    if (hit) try { ui.connecting = null; connectPort(completed.nodeId, completed.portId); connectPort(hit.dataset.portNode, hit.dataset.portId); } catch (err) { msg(err.message, true); }
  } else if (['window', 'resize'].includes(completed.kind)) { rememberWindow(ui.floats.find(f => f.id === completed.id)); markDirty(); renderFloats(); }
  else { markDirty(completed.kind === 'draw-port' ? mod() : project()); render(); }
});
root.addEventListener('pointercancel', () => { pointer = null; render(); });
root.addEventListener('click', e => {
  const target = e.target, action = target.closest('[data-action]');
  if (Date.now() < (ui.ignoreClickUntil || 0) && !action) return;
  try {
    if (action && !action.disabled) { contextMenu = null; handleAction(action.dataset.action, action); return; }
    if (modal) return;
    const port = target.closest('[data-port-node]'), quick = target.closest('[data-quick-node]'), node = target.closest('[data-node]'), edge = target.closest('[data-edge]'), draw = target.closest('[data-draw-id]');
    if (port) connectPort(port.dataset.portNode, port.dataset.portId);
    else if (quick) openDevice(quick.dataset.quickNode);
    else if (node) { ui.selectedNode = node.dataset.node; ui.selectedEdge = ''; syncDeviceSelection(); }
    else if (edge) { ui.selectedEdge = edge.dataset.edge; ui.selectedNode = ''; render(); }
    else if (draw) { ui.editorPort = draw.dataset.drawId; render(); }
    else if (target.closest('#network') && ui.placing) newInstance(ui.placing, svgPoint(document.getElementById('network'), e));
    else if (target.closest('[data-chart-hit]')) { ui.pinnedChart = ui.pinnedChart ? null : target.closest('svg').id; chartHover(e, true); }
    else if (contextMenu) { contextMenu = null; renderFloats(); }
  } catch (err) { msg(err.message, true); }
});
root.addEventListener('dblclick', e => { const n = e.target.closest('[data-node]'); if (n && !e.target.closest('[data-port-node]')) openDevice(n.dataset.node); });
root.addEventListener('contextmenu', e => {
  const n = e.target.closest('[data-node]'); if (!n) return; e.preventDefault(); ui.selectedNode = n.dataset.node;
  contextMenu = { id: n.dataset.node, x: clamp(e.clientX, 70, innerWidth - 202), y: clamp(e.clientY, 60, innerHeight - 370) }; syncDeviceSelection(); renderFloats();
});
function selectCodeTarget(kind) {
  if (!['runtime', 'header', 'design'].includes(kind)) return;
  ui.codeKind = kind;
  const picker = root.querySelector('[data-code-target]'); if (picker) picker.value = kind;
  saveUI();
}
root.addEventListener('pointerover', e => { if (!pointer) showCanvasInspection(e.target); });
root.addEventListener('pointerout', e => { if (!pointer) showCanvasInspection(e.relatedTarget); });
root.addEventListener('focusin', e => { if (e.target.closest('#network [data-node]')) showCanvasInspection(e.target); if (e.target.matches('textarea[data-code-kind]')) selectCodeTarget(e.target.dataset.codeKind); });
root.addEventListener('focusout', e => { if (e.target.closest('#network [data-node]')) showCanvasInspection(e.relatedTarget); });
root.addEventListener('scroll', e => { if (e.target.matches?.('textarea[data-code-kind]')) e.target.previousElementSibling.scrollTop = e.target.scrollTop; }, true);
root.addEventListener('input', e => { try { handleInput(e.target); } catch (err) { msg(err.message, true); } });
root.addEventListener('change', e => { try { handleChange(e.target); } catch (err) { e.target.setAttribute('aria-invalid', 'true'); msg(err.message, true); } });
root.addEventListener('submit', e => {
  if (e.target.getAttribute('id') !== 'dialog-form') return; e.preventDefault();
  const current = modal; if (!current?.onSubmit) return;
  try { current.onSubmit(Object.fromEntries(new FormData(e.target))); if (modal === current) closeDialog(); }
  catch (err) { const target = document.getElementById('dialog-error'); if (target) { target.hidden = false; target.textContent = err.message; } }
});
root.addEventListener('dragstart', e => { const el = e.target.closest('[data-drag-module]'); if (el) { e.dataTransfer.setData('text/plain', el.dataset.dragModule); e.dataTransfer.effectAllowed = 'copy'; } });
root.addEventListener('dragover', e => { if (e.target.closest('#network-area')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
root.addEventListener('drop', e => {
  if (!e.target.closest('#network-area')) return; e.preventDefault();
  const id = e.dataTransfer.getData('text/plain'); if (state.modules.some(m => m.id === id)) try { newInstance(id, svgPoint(document.getElementById('network'), e)); } catch (err) { msg(err.message, true); }
});
function chartHover(e, force = false) {
  const svg = e.target.closest?.('svg[data-chart]'); if (!svg || ui.pinnedChart && !force) return;
  const data = chartRegistry.get(svg.id); if (!data?.rows.length) return;
  const p = svgPoint(svg, e), x = clamp(p.x, data.left, data.right), t = data.minT + (x - data.left) / (data.right - data.left) * (data.maxT - data.minT);
  ui.chartCursor = { id: svg.id, time: t };
  paintChartCursor(svg.id, t, ui.pinnedChart === svg.id);
  restoreChartCursor();
}
document.addEventListener('keydown', e => {
  const edit = e.target.matches('input,textarea,select,[contenteditable=true]');
  if (modal && e.key === 'Tab') {
    const items = [...document.getElementById('dialog-form').querySelectorAll('button:not(:disabled),input:not(:disabled),textarea,select')].filter(e => e.getClientRects().length);
    if (!e.shiftKey && e.target === items.at(-1)) { e.preventDefault(); items[0].focus(); } else if (e.shiftKey && e.target === items[0]) { e.preventDefault(); items.at(-1).focus(); } return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveAll(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); pageMap(); return; }
  if (e.key === 'Escape') { closeDialog(); contextMenu = null; ui.connecting = null; ui.placing = null; ui.pinnedChart = null; render(); return; }
  if (edit) {
    if (e.key === 'Tab' && e.target.tagName === 'TEXTAREA' && (e.target.dataset.codeKind || 'controlCode' in e.target.dataset)) { e.preventDefault(); const el = e.target; el.setRangeText(el.dataset.codeKind ? '    ' : '  ', el.selectionStart, el.selectionEnd, 'end'); el.dispatchEvent(new Event('input', { bubbles: true })); }
    return;
  }
  if (modal) return;
  if (e.key === 'Enter' || e.key === ' ') {
    const p = e.target.closest('[data-port-node]'), n = e.target.closest('[data-node]'), draw = e.target.closest('[data-draw-id]');
    if (p || n || draw) { e.preventDefault(); if (p) { try { connectPort(p.dataset.portNode, p.dataset.portId); } catch (err) { msg(err.message, true); } } else if (n) openDevice(n.dataset.node); else { ui.editorPort = draw.dataset.drawId; render(); } return; }
  }
  if (ui.route === 'workbench') {
    if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.toLowerCase() === 'r' && ui.selectedNode) { e.preventDefault(); rotateDevice(ui.selectedNode, e.shiftKey ? -1 : 1); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(e.shiftKey); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); undo(true); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') copyDevice();
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') { e.preventDefault(); pasteDevice(); }
    else if (e.key === 'Delete') { if (ui.selectedNode) deleteNode(ui.selectedNode); else if (ui.selectedEdge) deleteEdge(ui.selectedEdge); }
  }
  if (ui.route === 'editor' && ui.moduleTab === 'drawing' && e.key.startsWith('Arrow')) {
    const p = mod().ports.find(p => p.id === ui.editorPort); if (!p) return;
    e.preventDefault(); p.x = clamp(p.x + (e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0), 5, 95); p.y = clamp(p.y + (e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0), 10, 85); markDirty(mod()); render();
  }
});
// Saves and exports made before a built-in parameter existed (e.g. pipe heat loss / ambient)
// get its default in module variables/values/banks, models and instances. Idempotent.
function backfillBuiltinParams(data) {
  const builtin = (data.modules || []).filter(m => m && m.runtime !== 'python' && PARAM_DEFS[m.kind]);
  for (const m of builtin) {
    if (!Array.isArray(m.variables)) continue;
    for (const v of variablesFor({kind:m.kind, ports:[]}).filter(v => v.origin === 'parameter' || v.origin === 'runtime')) {
      if (m.variables.some(x => x.id === v.id)) continue;
      const before = m.variables.findIndex(x => x.origin === 'system');
      m.variables.splice(before < 0 ? m.variables.length : before, 0, v);
      if (m.values && !(v.id in m.values)) m.values[v.id] = clone(v.value);
      (m.banks || []).forEach(bank => { if (bank && !(v.id in bank)) bank[v.id] = clone(v.value); });
    }
  }
  const fill = (params, kind) => { if (params && typeof params === 'object') for (const f of PARAM_DEFS[kind]) if (!(f[0] in params)) params[f[0]] = f[6]; };
  const kindOf = id => builtin.find(m => m.id === id)?.kind;
  for (const item of data.models || []) { const kind = kindOf(item?.moduleId); if (kind) { fill(item.params, kind); (item.versions || []).forEach(v => fill(v?.params, kind)); } }
  for (const p of data.projects || []) for (const pg of p?.pages || []) for (const n of pg?.nodes || []) {
    const kind = !p.moduleSnapshots?.[n?.moduleId] && kindOf(n?.moduleId);
    if (kind) { fill(n.params, kind); fill(n.draft, kind); }
  }
}
function normalizeState() {
  normalizeModuleGroups();
  state.modules.forEach(m => { m.saving=false; if (m.manifest) PARAM_DEFS[m.kind] = manifestFields(m.manifest); normalizePythonSource(m); });
  backfillBuiltinParams(state);
  state.windowPositions ||= {}; state.charts ||= {}; state.charts.series ||= {q:true,a:true,b:true}; state.charts.extra ||= []; state.charts.range ||= 'window'; state.serial ||= 30; state.messages ||= [];
  // 兼容旧草稿：运行快照/验证台/项目运行可能缺少 history、events、values 等字段（例如被裁剪过的草稿），
  // 补齐默认值后继续打开与保存，而不是让 normalizeState 抛错、整份草稿被内置示例覆盖。
  state.records = Array.isArray(state.records) ? state.records : [];
  for (const record of state.records) { record.history = Array.isArray(record.history) ? record.history : []; record.events = Array.isArray(record.events) ? record.events : []; }
  state.bench ||= {}; state.bench.run ||= emptyRun('bench');
  const benchModule = state.bench && state.modules.find(m => m.id === state.bench.moduleId);
  if (benchModule?.runtime === 'python') { state.bench.params ||= {}; for (const spec of manifestParamSpecs(benchModule.manifest)) if (!(spec.id in state.bench.params)) state.bench.params[spec.id] = clone(spec.default); }
  for (const p of state.projects) {
    p.scenarios ||= [];p.activeScenarioId ||= '';
    engine.pinProject(p,true);
    controls.normalize(p);
    if (!p.run || typeof p.run !== 'object') p.run = emptyRun();
    if (p.run.source !== 'engine') p.run = emptyRun();
    if (p.run.status === 'solving') p.run.status = 'ready';
    p.run.events ||= []; p.run.history ||= []; p.run.values ||= emptyRun().values;
    for (const pg of p.pages) { pg.zoom ||= 1; pg.pan ||= [0, 0]; for (const n of pg.nodes) { const m = moduleOf(n); if (m.runtime === 'python') for (const spec of manifestParamSpecs(m.manifest)) { if (!(spec.id in n.params)) n.params[spec.id] = clone(spec.default); if (!n.draft || !(spec.id in n.draft)) { n.draft ||= clone(n.params); n.draft[spec.id] = clone(n.params[spec.id]); } } n.draft ||= clone(n.params); validateInstanceVariableState(n, m); ensureInstanceVariables(n, m, p); } }
    const variables = projectVariables(p);
    for (const field of ['input', 'output']) if (!variables.some(v => v.id === p.controlConfig[field])) {
      const legacy = variables.find(v => v.legacyId === p.controlConfig[field]); if (legacy) p.controlConfig[field] = legacy.id;
    }
  }
  if (state.bench.run.status === 'solving') state.bench.run.status = 'ready';
  state.bench.run.events ||= []; state.bench.run.history ||= []; state.bench.run.values ||= emptyRun().values;
}
const chartRegistry = new Map();
engine = window.createEngineClient({state:()=>state, project, parameterKey:projectParameterKey, moduleOf,
  persist:()=>persistLocal(),
  restoreWorkspace,validateWorkspace:validateImport,archives:receiveArchives,showArchive,
  moduleOutput:(m,text)=>{m.authoringOutput=text;if(m.id===state.selectedModule){const el=document.getElementById('module-output') || document.getElementById('code-output');if(el){el.textContent=text;document.getElementById('authoring-diagnostics')?.remove();el.insertAdjacentHTML('afterend',renderAuthoringDiagnostics(m));}}},
  parameterDefinitions:PARAM_DEFS, emptyRun, render:()=>retainFocus(), refresh:refreshLive,
  message:msg, diagnostics:showDiagnostics, dirty:markDirty,
  askToken:(reason,done)=>openDialog('输入访问令牌',reason+'令牌由服务端管理员用 python -m fn_engine token create 生成，只保存在当前浏览器标签页。',
    `<label class="field"><span>访问令牌</span><input name="token" type="password" autocomplete="off" required aria-label="访问令牌" placeholder="fn_…"></label>`,
    data=>{if(!data.token?.trim())throw Error('请输入令牌。');done(data.token);},'连接')});
scenarioBatches=window.createScenarioBatchesUI({engine:()=>engine,ui:()=>ui,project,projectKey:projectParameterKey,
  esc,btn,heading,msg,render,confirm:confirmChange,download:downloadFile});
workflows=window.createModelingWorkflows({state:()=>state,engine:()=>engine,ui:()=>ui,project,
  esc,btn,openDialog,closeDialog,msg,clone,uid,emptyRun,confirm:confirmChange,paramSpecs:deviceParamSpecs,
  projectKey:projectParameterKey,dirty:markDirty,render,persist:()=>persistLocal(),download:downloadFile,
  replaceState:next=>{validateImport(next);const previous=state;try{state=next;normalizeState();ui.floats=[];ui.selectedNode='';undoStack=[];redoStack=[];}catch(error){state=previous;throw error;}}});
coldStorage=window.createColdStorageUI({state:()=>state,engine:()=>engine,ui:()=>ui,makeInstance,makeProject,project,
  uid,normalizeState,markDirty,persist:()=>persistLocal(),openProject,msg,esc,btn,openDialog,closeDialog,render,fitNetwork,remember,moduleOf,
  download:downloadFile,projectKey:projectParameterKey});
try { normalizeState(); } catch { state = initialState(); normalizeState(); recovery = '原型记录不完整，已恢复内置示例。'; }
function routeFromLocation() {
  const route = location.hash.slice(1);
  if (PAGE_META[route]) return route;
  if (route) history.replaceState(null, '', '#home');
  return 'home';
}
ui.route = routeFromLocation();
render();
engine.init();
window.addEventListener('hashchange', () => { ui.route = routeFromLocation(); render(); });
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { renderFloats(); if (['curves', 'workbench'].includes(ui.route)) refreshLive(); }, 120); });
runInterval = setInterval(() => engine.tick(), 200);

})();
