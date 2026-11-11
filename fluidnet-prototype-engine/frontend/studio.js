import {FluidNetPumpCurveEditor} from './pump-curve-editor.js';
import {DeviceBatchEditor} from './device-batch.js';
import {EquipmentSelection} from './equipment-selection.js';
import {FluidNetActionRouter} from './action-router.js';
import {FluidNetApiExamples} from './api-examples.js';
import {FluidNetCanvasSymbols} from './canvas-symbols.js';
import {FluidNetCanvasWorkspace} from './canvas-workspace.js';
import {FluidNetControls} from './control-programs.js';
import {FluidNetDeviceApplication} from './device-application.js';
import {FluidNetDeviceWindows} from './device-windows.js';
import {FluidNetDraftStore} from './draft-store.js';
import {FluidNetLinks} from './project-links.js';
import {FluidNetDeviceGuide} from './device-guide.js';
import {FluidNetModuleEditorView} from './module-editor-view.js';
import {FluidNetPanelLayout} from './panel-layout.js';
import {FluidNetPathTrace} from './path-trace.js';
import {FluidNetPerformanceData} from './performance-library.js';
import {FluidNetProjectEditing} from './project-editing.js';
import {FluidNetProjectModel} from './project-model.js';
import {FluidNetProjectRunState} from './project-run-state.js';
import {FluidNetProjectState} from './project-state.js';
import {FluidNetRunResultsView} from './run-results-view.js';
import {FluidNetSvgDom} from './svg-dom.js';
import {FluidNetWorkbenchRefresh} from './workbench-refresh.js';
import {FluidNetWorkspaceInteractions} from './workspace-interactions.js';
import {FluidNetWorkspaceNormalization} from './workspace-normalization.js';
import {FluidNetWorkspaceStorage} from './workspace-storage.js';
import {ModuleTestEditor} from './module-test-editor.js';
import {createAirSideUI} from './air-side.js';
import {createColdStorageUI} from './cold-storage.js';
import {createDevicePanel} from './device-panel.js';
import {createEngineClient} from './engine-client.js';
import {createEquipmentLibrary} from './equipment-library.js';
import {createModelingWorkflows} from './modeling-workflows.js';
import {createModuleReplayUI} from './module-replay.js';
import {createScenarioBatchesUI} from './scenario-batches.js';
import {createSystemInspection} from './system-inspection.js';

export function startStudio() {
'use strict';
const ICONS = {"Activity":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-activity\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2\"></path></svg>","ArrowDownToLine":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-down-to-line\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 17V3\"></path><path d=\"m6 11 6 6 6-6\"></path><path d=\"M19 21H5\"></path></svg>","ArrowRight":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-right\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 12h14\"></path><path d=\"m12 5 7 7-7 7\"></path></svg>","ArrowRightLeft":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-right-left\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m16 3 4 4-4 4\"></path><path d=\"M20 7H4\"></path><path d=\"m8 21-4-4 4-4\"></path><path d=\"M4 17h16\"></path></svg>","ArrowUpRight":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-arrow-up-right\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M7 7h10v10\"></path><path d=\"M7 17 17 7\"></path></svg>","Bell":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-bell\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M10.268 21a2 2 0 0 0 3.464 0\"></path><path d=\"M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326\"></path></svg>","BookOpen":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-book-open\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 7v14\"></path><path d=\"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z\"></path></svg>","Box":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-box\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z\"></path><path d=\"m3.3 7 8.7 5 8.7-5\"></path><path d=\"M12 22V12\"></path></svg>","Boxes":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-boxes\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z\"></path><path d=\"m7 16.5-4.74-2.85\"></path><path d=\"m7 16.5 5-3\"></path><path d=\"M7 16.5v5.17\"></path><path d=\"M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z\"></path><path d=\"m17 16.5-5-3\"></path><path d=\"m17 16.5 4.74-2.85\"></path><path d=\"M17 16.5v5.17\"></path><path d=\"M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z\"></path><path d=\"M12 8 7.26 5.15\"></path><path d=\"m12 8 4.74-2.85\"></path><path d=\"M12 13.5V8\"></path></svg>","Braces":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-braces\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1\"></path><path d=\"M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1\"></path></svg>","Cable":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-cable\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M17 21v-2a1 1 0 0 1-1-1v-1a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1a1 1 0 0 1-1 1\"></path><path d=\"M19 15V6.5a1 1 0 0 0-7 0v11a1 1 0 0 1-7 0V9\"></path><path d=\"M21 21v-2h-4\"></path><path d=\"M3 5h4V3\"></path><path d=\"M7 5a1 1 0 0 1 1 1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1V3\"></path></svg>","Check":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-check\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 6 9 17l-5-5\"></path></svg>","CheckCheck":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-check-check\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M18 6 7 17l-5-5\"></path><path d=\"m22 10-7.5 7.5L13 16\"></path></svg>","CheckCircle2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-check\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"m9 12 2 2 4-4\"></path></svg>","ChevronDown":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-chevron-down\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m6 9 6 6 6-6\"></path></svg>","ChevronLeft":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-chevron-left\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m15 18-6-6 6-6\"></path></svg>","ChevronRight":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-chevron-right\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m9 18 6-6-6-6\"></path></svg>","Circle":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle></svg>","CircleDot":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-dot\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><circle cx=\"12\" cy=\"12\" r=\"1\"></circle></svg>","CircleHelp":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-help\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3\"></path><path d=\"M12 17h.01\"></path></svg>","CirclePlus":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-circle-plus\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"M8 12h8\"></path><path d=\"M12 8v8\"></path></svg>","Clipboard":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-clipboard\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"8\" height=\"4\" x=\"8\" y=\"2\" rx=\"1\" ry=\"1\"></rect><path d=\"M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2\"></path></svg>","Clock3":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-clock3\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><polyline points=\"12 6 12 12 16.5 12\"></polyline></svg>","Code2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-code-xml\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m18 16 4-4-4-4\"></path><path d=\"m6 8-4 4 4 4\"></path><path d=\"m14.5 4-5 16\"></path></svg>","Columns2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-columns2\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect><path d=\"M12 3v18\"></path></svg>","Copy":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-copy\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"14\" height=\"14\" x=\"8\" y=\"8\" rx=\"2\" ry=\"2\"></rect><path d=\"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2\"></path></svg>","Database":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-database\" aria-hidden=\"true\" focusable=\"false\"><ellipse cx=\"12\" cy=\"5\" rx=\"9\" ry=\"3\"></ellipse><path d=\"M3 5V19A9 3 0 0 0 21 19V5\"></path><path d=\"M3 12A9 3 0 0 0 21 12\"></path></svg>","Download":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-download\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"></path><polyline points=\"7 10 12 15 17 10\"></polyline><line x1=\"12\" x2=\"12\" y1=\"15\" y2=\"3\"></line></svg>","Droplets":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-droplets\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z\"></path><path d=\"M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97\"></path></svg>","Ellipsis":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-ellipsis\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"1\"></circle><circle cx=\"19\" cy=\"12\" r=\"1\"></circle><circle cx=\"5\" cy=\"12\" r=\"1\"></circle></svg>","ExternalLink":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-external-link\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 3h6v6\"></path><path d=\"M10 14 21 3\"></path><path d=\"M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6\"></path></svg>","Eye":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-eye\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0\"></path><circle cx=\"12\" cy=\"12\" r=\"3\"></circle></svg>","FileCode2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-file-code2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4\"></path><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"></path><path d=\"m5 12-3 3 3 3\"></path><path d=\"m9 18 3-3-3-3\"></path></svg>","FileJson":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-file-json\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\"></path><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"></path><path d=\"M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1\"></path><path d=\"M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1\"></path></svg>","FileText":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-file-text\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\"></path><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"></path><path d=\"M10 9H8\"></path><path d=\"M16 13H8\"></path><path d=\"M16 17H8\"></path></svg>","Filter":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-filter\" aria-hidden=\"true\" focusable=\"false\"><polygon points=\"22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3\"></polygon></svg>","Flame":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-flame\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z\"></path></svg>","Folder":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-folder\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\"></path></svg>","FolderOpen":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-folder-open\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2\"></path></svg>","Gauge":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-gauge\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m12 14 4-4\"></path><path d=\"M3.34 19a10 10 0 1 1 17.32 0\"></path></svg>","GitBranch":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-git-branch\" aria-hidden=\"true\" focusable=\"false\"><line x1=\"6\" x2=\"6\" y1=\"3\" y2=\"15\"></line><circle cx=\"18\" cy=\"6\" r=\"3\"></circle><circle cx=\"6\" cy=\"18\" r=\"3\"></circle><path d=\"M18 9a9 9 0 0 1-9 9\"></path></svg>","GitCompareArrows":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-git-compare-arrows\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"5\" cy=\"6\" r=\"3\"></circle><path d=\"M12 6h5a2 2 0 0 1 2 2v7\"></path><path d=\"m15 9-3-3 3-3\"></path><circle cx=\"19\" cy=\"18\" r=\"3\"></circle><path d=\"M12 18H7a2 2 0 0 1-2-2V9\"></path><path d=\"m9 15 3 3-3 3\"></path></svg>","Grid2X2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-grid2x2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 3v18\"></path><path d=\"M3 12h18\"></path><rect x=\"3\" y=\"3\" width=\"18\" height=\"18\" rx=\"2\"></rect></svg>","Grip":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-grip\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"5\" r=\"1\"></circle><circle cx=\"19\" cy=\"5\" r=\"1\"></circle><circle cx=\"5\" cy=\"5\" r=\"1\"></circle><circle cx=\"12\" cy=\"12\" r=\"1\"></circle><circle cx=\"19\" cy=\"12\" r=\"1\"></circle><circle cx=\"5\" cy=\"12\" r=\"1\"></circle><circle cx=\"12\" cy=\"19\" r=\"1\"></circle><circle cx=\"19\" cy=\"19\" r=\"1\"></circle><circle cx=\"5\" cy=\"19\" r=\"1\"></circle></svg>","GripVertical":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-grip-vertical\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"9\" cy=\"12\" r=\"1\"></circle><circle cx=\"9\" cy=\"5\" r=\"1\"></circle><circle cx=\"9\" cy=\"19\" r=\"1\"></circle><circle cx=\"15\" cy=\"12\" r=\"1\"></circle><circle cx=\"15\" cy=\"5\" r=\"1\"></circle><circle cx=\"15\" cy=\"19\" r=\"1\"></circle></svg>","History":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-history\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\"></path><path d=\"M3 3v5h5\"></path><path d=\"M12 7v5l4 2\"></path></svg>","Home":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-house\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8\"></path><path d=\"M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\"></path></svg>","Info":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-info\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><path d=\"M12 16v-4\"></path><path d=\"M12 8h.01\"></path></svg>","Keyboard":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-keyboard\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M10 8h.01\"></path><path d=\"M12 12h.01\"></path><path d=\"M14 8h.01\"></path><path d=\"M16 12h.01\"></path><path d=\"M18 8h.01\"></path><path d=\"M6 8h.01\"></path><path d=\"M7 16h10\"></path><path d=\"M8 12h.01\"></path><rect width=\"20\" height=\"16\" x=\"2\" y=\"4\" rx=\"2\"></rect></svg>","Layers":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-layers\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z\"></path><path d=\"M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12\"></path><path d=\"M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17\"></path></svg>","LayoutDashboard":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-layout-dashboard\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"7\" height=\"9\" x=\"3\" y=\"3\" rx=\"1\"></rect><rect width=\"7\" height=\"5\" x=\"14\" y=\"3\" rx=\"1\"></rect><rect width=\"7\" height=\"9\" x=\"14\" y=\"12\" rx=\"1\"></rect><rect width=\"7\" height=\"5\" x=\"3\" y=\"16\" rx=\"1\"></rect></svg>","List":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-list\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12h.01\"></path><path d=\"M3 18h.01\"></path><path d=\"M3 6h.01\"></path><path d=\"M8 12h13\"></path><path d=\"M8 18h13\"></path><path d=\"M8 6h13\"></path></svg>","ListChecks":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-list-checks\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m3 17 2 2 4-4\"></path><path d=\"m3 7 2 2 4-4\"></path><path d=\"M13 6h8\"></path><path d=\"M13 12h8\"></path><path d=\"M13 18h8\"></path></svg>","Lock":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-lock\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"11\" x=\"3\" y=\"11\" rx=\"2\" ry=\"2\"></rect><path d=\"M7 11V7a5 5 0 0 1 10 0v4\"></path></svg>","Maximize2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-maximize2\" aria-hidden=\"true\" focusable=\"false\"><polyline points=\"15 3 21 3 21 9\"></polyline><polyline points=\"9 21 3 21 3 15\"></polyline><line x1=\"21\" x2=\"14\" y1=\"3\" y2=\"10\"></line><line x1=\"3\" x2=\"10\" y1=\"21\" y2=\"14\"></line></svg>","MessageSquare":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-message-square\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z\"></path></svg>","Minimize2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-minimize2\" aria-hidden=\"true\" focusable=\"false\"><polyline points=\"4 14 10 14 10 20\"></polyline><polyline points=\"20 10 14 10 14 4\"></polyline><line x1=\"14\" x2=\"21\" y1=\"10\" y2=\"3\"></line><line x1=\"3\" x2=\"10\" y1=\"21\" y2=\"14\"></line></svg>","Minus":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-minus\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 12h14\"></path></svg>","Monitor":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-monitor\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"20\" height=\"14\" x=\"2\" y=\"3\" rx=\"2\"></rect><line x1=\"8\" x2=\"16\" y1=\"21\" y2=\"21\"></line><line x1=\"12\" x2=\"12\" y1=\"17\" y2=\"21\"></line></svg>","Moon":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-moon\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z\"></path></svg>","MoreHorizontal":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-ellipsis\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"1\"></circle><circle cx=\"19\" cy=\"12\" r=\"1\"></circle><circle cx=\"5\" cy=\"12\" r=\"1\"></circle></svg>","MousePointer2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-mouse-pointer2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.063z\"></path></svg>","Move":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-move\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 2v20\"></path><path d=\"m15 19-3 3-3-3\"></path><path d=\"m19 9 3 3-3 3\"></path><path d=\"M2 12h20\"></path><path d=\"m5 9-3 3 3 3\"></path><path d=\"m9 5 3-3 3 3\"></path></svg>","Network":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-network\" aria-hidden=\"true\" focusable=\"false\"><rect x=\"16\" y=\"16\" width=\"6\" height=\"6\" rx=\"1\"></rect><rect x=\"2\" y=\"16\" width=\"6\" height=\"6\" rx=\"1\"></rect><rect x=\"9\" y=\"2\" width=\"6\" height=\"6\" rx=\"1\"></rect><path d=\"M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3\"></path><path d=\"M12 12V8\"></path></svg>","PanelLeftClose":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-panel-left-close\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect><path d=\"M9 3v18\"></path><path d=\"m16 15-3-3 3-3\"></path></svg>","PanelLeftOpen":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-panel-left-open\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect><path d=\"M9 3v18\"></path><path d=\"m14 9 3 3-3 3\"></path></svg>","Pause":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-pause\" aria-hidden=\"true\" focusable=\"false\"><rect x=\"14\" y=\"4\" width=\"4\" height=\"16\" rx=\"1\"></rect><rect x=\"6\" y=\"4\" width=\"4\" height=\"16\" rx=\"1\"></rect></svg>","Pencil":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-pencil\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z\"></path><path d=\"m15 5 4 4\"></path></svg>","Pin":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-pin\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 17v5\"></path><path d=\"M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z\"></path></svg>","Play":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-play\" aria-hidden=\"true\" focusable=\"false\"><polygon points=\"6 3 20 12 6 21 6 3\"></polygon></svg>","Plug":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-plug\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 22v-5\"></path><path d=\"M9 8V2\"></path><path d=\"M15 8V2\"></path><path d=\"M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z\"></path></svg>","Plus":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-plus\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 12h14\"></path><path d=\"M12 5v14\"></path></svg>","Redo2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-redo2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m15 14 5-5-5-5\"></path><path d=\"M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13\"></path></svg>","RefreshCw":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-refresh-cw\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8\"></path><path d=\"M21 3v5h-5\"></path><path d=\"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16\"></path><path d=\"M8 16H3v5\"></path></svg>","RotateCcw":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-rotate-ccw\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\"></path><path d=\"M3 3v5h5\"></path></svg>","RotateCw":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-rotate-cw\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8\"></path><path d=\"M21 3v5h-5\"></path></svg>","Save":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-save\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z\"></path><path d=\"M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7\"></path><path d=\"M7 3v4a1 1 0 0 0 1 1h7\"></path></svg>","Scan":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-scan\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 7V5a2 2 0 0 1 2-2h2\"></path><path d=\"M17 3h2a2 2 0 0 1 2 2v2\"></path><path d=\"M21 17v2a2 2 0 0 1-2 2h-2\"></path><path d=\"M7 21H5a2 2 0 0 1-2-2v-2\"></path></svg>","Search":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-search\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"11\" cy=\"11\" r=\"8\"></circle><path d=\"m21 21-4.3-4.3\"></path></svg>","Settings2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-settings2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 7h-9\"></path><path d=\"M14 17H5\"></path><circle cx=\"17\" cy=\"17\" r=\"3\"></circle><circle cx=\"7\" cy=\"7\" r=\"3\"></circle></svg>","ShieldCheck":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-shield-check\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z\"></path><path d=\"m9 12 2 2 4-4\"></path></svg>","SlidersHorizontal":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-sliders-horizontal\" aria-hidden=\"true\" focusable=\"false\"><line x1=\"21\" x2=\"14\" y1=\"4\" y2=\"4\"></line><line x1=\"10\" x2=\"3\" y1=\"4\" y2=\"4\"></line><line x1=\"21\" x2=\"12\" y1=\"12\" y2=\"12\"></line><line x1=\"8\" x2=\"3\" y1=\"12\" y2=\"12\"></line><line x1=\"21\" x2=\"16\" y1=\"20\" y2=\"20\"></line><line x1=\"12\" x2=\"3\" y1=\"20\" y2=\"20\"></line><line x1=\"14\" x2=\"14\" y1=\"2\" y2=\"6\"></line><line x1=\"8\" x2=\"8\" y1=\"10\" y2=\"14\"></line><line x1=\"16\" x2=\"16\" y1=\"18\" y2=\"22\"></line></svg>","Square":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-square\" aria-hidden=\"true\" focusable=\"false\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\"></rect></svg>","SquareDashed":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-square-dashed\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M5 3a2 2 0 0 0-2 2\"></path><path d=\"M19 3a2 2 0 0 1 2 2\"></path><path d=\"M21 19a2 2 0 0 1-2 2\"></path><path d=\"M5 21a2 2 0 0 1-2-2\"></path><path d=\"M9 3h1\"></path><path d=\"M9 21h1\"></path><path d=\"M14 3h1\"></path><path d=\"M14 21h1\"></path><path d=\"M3 9v1\"></path><path d=\"M21 9v1\"></path><path d=\"M3 14v1\"></path><path d=\"M21 14v1\"></path></svg>","Star":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-star\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z\"></path></svg>","StepForward":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-step-forward\" aria-hidden=\"true\" focusable=\"false\"><line x1=\"6\" x2=\"6\" y1=\"4\" y2=\"20\"></line><polygon points=\"10,4 20,12 10,20\"></polygon></svg>","Sun":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-sun\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"12\" r=\"4\"></circle><path d=\"M12 2v2\"></path><path d=\"M12 20v2\"></path><path d=\"m4.93 4.93 1.41 1.41\"></path><path d=\"m17.66 17.66 1.41 1.41\"></path><path d=\"M2 12h2\"></path><path d=\"M20 12h2\"></path><path d=\"m6.34 17.66-1.41 1.41\"></path><path d=\"m19.07 4.93-1.41 1.41\"></path></svg>","Table2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-table2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18\"></path></svg>","Terminal":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-terminal\" aria-hidden=\"true\" focusable=\"false\"><polyline points=\"4 17 10 11 4 5\"></polyline><line x1=\"12\" x2=\"20\" y1=\"19\" y2=\"19\"></line></svg>","Thermometer":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-thermometer\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z\"></path></svg>","Trash2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-trash2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3 6h18\"></path><path d=\"M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6\"></path><path d=\"M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2\"></path><line x1=\"10\" x2=\"10\" y1=\"11\" y2=\"17\"></line><line x1=\"14\" x2=\"14\" y1=\"11\" y2=\"17\"></line></svg>","Triangle":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-triangle\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M13.73 4a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z\"></path></svg>","Undo2":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-undo2\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M9 14 4 9l5-5\"></path><path d=\"M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11\"></path></svg>","Upload":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-upload\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"></path><polyline points=\"17 8 12 3 7 8\"></polyline><line x1=\"12\" x2=\"12\" y1=\"3\" y2=\"15\"></line></svg>","Waypoints":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-waypoints\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"12\" cy=\"4.5\" r=\"2.5\"></circle><path d=\"m10.2 6.3-3.9 3.9\"></path><circle cx=\"4.5\" cy=\"12\" r=\"2.5\"></circle><path d=\"M7 12h10\"></path><circle cx=\"19.5\" cy=\"12\" r=\"2.5\"></circle><path d=\"m13.8 17.7 3.9-3.9\"></path><circle cx=\"12\" cy=\"19.5\" r=\"2.5\"></circle></svg>","Wind":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-wind\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12.8 19.6A2 2 0 1 0 14 16H2\"></path><path d=\"M17.5 8a2.5 2.5 0 1 1 2 4H2\"></path><path d=\"M9.8 4.4A2 2 0 1 1 11 8H2\"></path></svg>","Wrench":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-wrench\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z\"></path></svg>","X":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-x\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M18 6 6 18\"></path><path d=\"m6 6 12 12\"></path></svg>","Zap":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-zap\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z\"></path></svg>","Snowflake":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-snowflake\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12 2v20M3.34 7l17.32 10M3.34 17 20.66 7\"></path><path d=\"m9 4 3 3 3-3m-6 16 3-3 3 3M4 10l4-1-1-4m10 14-1-4 4-1M7 19l1-4-4-1M20 10l-4-1 1-4\"></path></svg>","GitMerge":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.65\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-git-merge\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"6\" cy=\"5\" r=\"3\"></circle><path d=\"M6 8v10m0-9a9 9 0 0 0 9 9\"></path><circle cx=\"6\" cy=\"21\" r=\"1\"></circle><circle cx=\"18\" cy=\"18\" r=\"3\"></circle></svg>"};
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
let moduleReplay;
let systemInspection;
let workflows = null;
let airSide = {markup:()=>'',afterRender:()=>{},action:async()=>{},refresh:()=>{}};
let scenarioBatches = {markup:()=>'',afterRender:()=>{},action:async()=>{}};
let coldStorage = {markup:()=>'',refresh:()=>{},action:async()=>{},couplingToolbar:()=>'',couplingReferences:()=>[],assertCouplingIdle:()=>{},syncCouplingCharts:()=>{},couplingChartBindings:()=>[]};
const UI_KEY = STORAGE_KEY + '-ui';
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
  air:['风系统','Wind','风量、热湿状态与水耗'],
  batches:['批量','ListChecks','批量工况、结果存档与方案比较'],
  controls:['控制','Code2','控制逻辑与观察变量'],
  connections:['对接','Plug','变量接口、访问令牌与串口'],
  settings:['设置','Settings2','介质、求解与显示'],
  help:['指南','BookOpen','页面导览与使用流程']
};
const EDITOR_TABS = [['drawing','设备与端口','SquareDashed'],['attributes','常用参数','SlidersHorizontal'],['code','算法','Code2'],['models','设备型号','Database'],['values','参数库值','Table2'],['channels','内部通路','Waypoints']];
const DOMAINS = { fluid:{label:'流体',color:'orange',unit:'kg/s',icon:'Droplets'}, thermal:{label:'传热',color:'blue',unit:'W',icon:'Thermometer'}, refrigerant:{label:'制冷剂',color:'green',unit:'kg/s',icon:'Droplets'}, info:{label:'信息',color:'green',unit:'—',icon:'Activity'}, power:{label:'电力',color:'purple',unit:'A',icon:'Zap'}, mech:{label:'机械',color:'blue',unit:'N·m',icon:'RotateCw'} };
// Port name prefixes for ports added in the module editor (station refrigerant ports are built-in only).
const PORT_PREFIX = { fluid: ['IM', 'EX'], info: ['II', 'IO'], power: ['PI', 'PO'], mech: ['MI', 'MO'] };
const PARAM_DEFS = {
  source:[['pressure','绝对压力','kPa',110,1000,1,201.325],['temperature','温度','°C',-100,400,1,20],['humidity_ratio_kg_kg','含湿量（kg/kg干空气）','1',0,.2,.001,0]],
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
const projectModel=FluidNetProjectModel;
const projectState=FluidNetProjectState;
const projectRunState=FluidNetProjectRunState;
const {manifestFields,manifestParamSpecs,manifestParamDefaults}=projectModel;
const defaultsFor = id => Object.fromEntries((PARAM_DEFS[id]||[]).map(f=>[f[0],f[6]]));
// Full parameter model for Python modules: numbers drive the numeric quick controls,
// while boolean/text/curve keep their own editors instead of being forced into a number input.
function deviceParamSpecs(n) {
  const m = moduleOf(n);
  if (m.manifest) return manifestParamSpecs(m.manifest);
  const definition=engine?.catalog?.modules.find(d=>d.id===m.kind);
  return moduleParamDefs(m).map(f => {
    const key=engine?.catalog?.prototype_parameter_bindings[m.kind]?.[f[0]]||f[0];
    const spec=definition?.parameters.find(p=>p.id===key);
    return {id:f[0], label:f[1], value_type:'number',unit:f[2] ? {display_unit:f[2]} : null,
      minimum:f[3],maximum:f[4],default:f[6],display:f[2],writable:spec?.writable!==false,runtime:spec?.runtime};
  }).concat((definition?.parameters||[]).filter(p=>p.value_type&&p.value_type!=='number').map(p=>({...p,
    id:Object.keys(engine.catalog.prototype_parameter_bindings[m.kind]||{}).find(k=>engine.catalog.prototype_parameter_bindings[m.kind][k]===p.id)||p.id})));
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
function controlTemplate(kind) {
  if (kind === 'interlock') return `# 机房联锁：启动顺序 → 压差确认 → 低压差停机 → 工作泵切换。
MIN_DP_PA = 20000.
CONFIRM_S = 2.
SWITCH_S = 10.


def initialize(ctx):
    ctx.state["phase"] = "starting"
    ctx.state["switched"] = False


def step(ctx, dt_s):
    dp = ctx.read("Discharge.common.pressure_pa") - ctx.read("Suction.common.pressure_pa")
    if ctx.state["phase"] == "starting":
        ctx.write("Pump1.param.running", 1.)
        if ctx.time_s >= CONFIRM_S:
            if dp < MIN_DP_PA:
                ctx.write("Pump1.param.running", 0.)
                ctx.write("Pump2.param.running", 0.)
                ctx.state["phase"] = "tripped"
            else:
                ctx.state["phase"] = "running"
    elif ctx.state["phase"] == "running" and not ctx.state["switched"] and ctx.time_s >= SWITCH_S:
        ctx.write("Pump2.param.running", 1.)
        ctx.write("Pump1.param.running", 0.)
        ctx.state["switched"] = True


def finalize(ctx):
    ctx.write("Pump1.param.running", 0.)
    ctx.write("Pump2.param.running", 0.)
`;
  return `def initialize(ctx):
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
const controls=FluidNetControls;
const links=FluidNetLinks;
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
try { const saved=FluidNetDraftStore.parse(localStorage.getItem(STORAGE_KEY)||'null');if(saved&&saved.schema===1&&Array.isArray(saved.projects)&&saved.projects.length&&Array.isArray(saved.modules)&&saved.modules.length&&Array.isArray(saved.models)){state=saved;state.projects.forEach(p=>{if(p.run.status==='running')p.run.status='paused';});if(state.bench.run.status==='running')state.bench.run.status='paused';} } catch { recovery='上次原型记录无法读取，已打开内置示例。'; }
const ui={route:'home',theme:matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light',modulePrecision:null,moduleTab:'drawing',selectedNode:'',selectedEdge:'',editorPort:'',category:'全部模块',moduleSearch:'',moduleView:'cards',projectSearch:'',projectFilter:'all',projectView:'grid',bank:0,allBanks:false,variableSearch:'',onlyCommon:false,valueSearch:'',arrayVar:'system:form',codeKind:'runtime',designIndex:0,modelSearch:'',modelFilter:'all',modelTab:'parameters',benchTab:'results',settingsTab:'project',connectionTab:'variables',selectedConnector:'serial1',nodeDomain:'fluid',nodeTab:'definition',selectedRecord:'DEMO-003',runFilter:'all',pageGrid:false,placing:null,connecting:null,canvasMode:'select',floats:[],frontId:'',floatSerial:0,taskDrawer:false,selectedChart:'q',clipboard:null,showLibrary:innerWidth>500,showChart:false,workbenchChart:'flow',compileOutput:'尚未检查。可检查 Python 括号与字符串，或预览模块调用流程。',controlOutput:'控制脚本尚未预览。',connectionSearch:'',guideStep:0};
try {const savedUI=JSON.parse(localStorage.getItem(UI_KEY)||'null');if(savedUI){for(const key of ['theme','modulePrecision','moduleTab','settingsTab','connectionTab','bank','pageGrid','codeKind','designIndex','showLibrary','showChart','workbenchChart','moduleView','canvasModeValue','canvasLabels','canvasAnimate','canvasScales'])if(savedUI[key]!==undefined)ui[key]=savedUI[key];}}catch{}
if (![null,2,4,6,8].includes(ui.modulePrecision)) ui.modulePrecision = null;
if (!['cards','list'].includes(ui.moduleView)) ui.moduleView = 'cards';
if (['design','header'].includes(ui.moduleTab)) { ui.codeKind=ui.moduleTab; ui.moduleTab='code'; }
if (!['runtime','design','header'].includes(ui.codeKind)) ui.codeKind='runtime';
if (![0,1,2].includes(ui.designIndex)) ui.designIndex=0;
let modal=null,contextMenu=null,toastTimer,runInterval,undoStack=[],redoStack=[],lastTick=0;
const project=()=>state.projects.find(p=>p.id===state.activeProject)||state.projects[0];
const activePage=()=>project().pages.find(p=>p.id===project().activePage)||project().pages[0];
const mod=(id=state.selectedModule)=>state.modules.find(m=>m.id===id)||state.modules[0];
const instance=id=>project().pages.flatMap(p=>p.nodes).find(n=>n.id===id);
const moduleOf=n=>ownerOfInstance(n)?.moduleSnapshots?.[n.moduleId] || mod(n.moduleId);
const model=(id=state.selectedModel)=>state.models.find(m=>m.id===id);
const moduleParamDefs=m=>m.manifest?manifestFields(m.manifest):m.parameterDefs||PARAM_DEFS[m.kind]||[];
const paramDefs=n=>moduleParamDefs(moduleOf(n));
const pendingCount=n=>deviceParamIds(n).filter(id=>!sameValue(n.draft[id],n.params[id])).length+instanceCustomPending(n)+(n.draftModelId&&(n.draftModelId!==n.modelId||n.draftModelVersion!==n.modelVersion)?1:0)+(FluidNetPerformanceData?.pending(n)?1:0);
const anyPending=()=>state.projects.reduce((sum,p)=>sum+p.pages.flatMap(p=>p.nodes).reduce((s,n)=>s+pendingCount(n),0),0);
const statusText=run=>({ready:'就绪',running:'运行中',paused:'已暂停',stopped:'已停止',completed:'已完成',failed:'失败',solving:'求解中'}[run.status]||'就绪');
function msg(text,error=false){const toast=document.getElementById('toast');toast.className='toast'+(error?' error':'');toast.innerHTML=icon(error?'Info':'CheckCircle2')+`<span>${esc(text)}</span>`;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.hidden=true,3500);document.getElementById('announcement').textContent=text;}
function saveUI(){try{localStorage.setItem(UI_KEY,JSON.stringify({theme:ui.theme,modulePrecision:ui.modulePrecision,moduleTab:ui.moduleTab,settingsTab:ui.settingsTab,connectionTab:ui.connectionTab,bank:ui.bank,pageGrid:ui.pageGrid,codeKind:ui.codeKind,designIndex:ui.designIndex,showLibrary:ui.showLibrary,showChart:ui.showChart,workbenchChart:ui.workbenchChart,moduleView:ui.moduleView,canvasModeValue:ui.canvasModeValue,canvasLabels:ui.canvasLabels,canvasAnimate:ui.canvasAnimate,canvasScales:ui.canvasScales}));}catch{/* 界面偏好体积很小；失败只影响主题/页签记忆，草稿失败由 persistLocal 提示。 */}}
// 草稿持久化和工作区替换由独立存储边界管理，状态仍由 shell 持有。
let workspaceStorageController;
function workspaceStorage(){return workspaceStorageController ||= FluidNetWorkspaceStorage.create({
  read:()=>state,write:value=>{state=value;},definitions:PARAM_DEFS,validate:validateImport,normalize:normalizeState,projectState,model:projectModel,storage:localStorage,key:STORAGE_KEY,draftStore:FluidNetDraftStore,
  ready:()=>engine.whenReady(),save:payload=>engine.saveWorkspace(payload),revision:()=>editRevision,
  status:()=>({phase:savePhase,error:saveError,localError:localSaveError,trimmed:localSaveTrimmed}),
  changed:patch=>{if('phase'in patch)savePhase=patch.phase;if('error'in patch)saveError=patch.error;if('localError'in patch)localSaveError=patch.localError;if('trimmed'in patch)localSaveTrimmed=patch.trimmed;syncChrome();},
  message:msg,resetView:()=>{ui.floats=[];ui.selectedNode='';undoStack=[];redoStack=[];editRevision++;},render,updateWindows:updateFloatBodies,pending:anyPending
});}
function persistLocal(){return workspaceStorage().persist();}
function backupLocalDraft(key,source=state){return workspaceStorage().backup(key,source);}
function markDirty(target){editRevision++;if(savePhase==='saved')savePhase='';projectState.markDirty(state,target);root.querySelectorAll("[data-float-save]").forEach(el=>el.textContent="草稿未保存");syncChrome();}
function saveAll(){return workspaceStorage().saveAll();}
function replaceWorkspaceState(data,beforeReplace=()=>{},afterNormalize=()=>{}){return workspaceStorage().replace(data,beforeReplace,afterNormalize);}
function restoreWorkspace(data){return workspaceStorage().restore(data);}
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
function receiveArchives(runs,observed){
  ui.archivedRuns=runs;projectRunState.reconcileArchives(state,runs,observed);
  if(ui.route==='runs')render();
}
function showArchive(record,overview){
  const source=record.request.project,overviewBindings=engine.overviewBindings(source);
  const chartBindings=source.thermal_couplings?.length?clone(state.charts.extra.filter(v=>v.projectId===source.id&&!isCouplingChart(v)))
    .concat(coldStorage.couplingChartBindings({id:source.id,thermalCouplings:source.thermal_couplings})):undefined;
  const item=projectRunState.archiveRecord(record,overview,{projectId:state.projects.find(p=>p.id===source.id)?.id,
    overviewBindings,overviewValues:engine.overviewValues,chartBindings});
  projectRunState.rememberArchive(state,item);ui.selectedRecord=item.id;render();
}
async function resumeArchiveDialog(id){
  const record=await engine.request('/runs/'+encodeURIComponent(id));
  const time=record.checkpoint_time_s;
  if(!record.checkpoint_available||!Number.isFinite(time))throw Error('该档案没有完整会话快照。');
  const original=record.request.duration_s;
  const proposed=Number.isFinite(original)&&original>time?original:Math.min(604800,time+Math.max(60,record.request.dt_s*100));
  openDialog('从快照续算',`从已接受的 ${number(time,3)} s 恢复物理库存与控制状态，另建项目副本并暂停，随后可单步或继续。`,
    `<label class="field"><span>新的绝对终止时刻 · s</span><input name="duration" type="number" step="any" min="${time}" max="604800" required value="${proposed}" aria-label="续算终止时刻"></label><p class="muted">终止时刻须晚于 ${number(time,3)} s。副本使用快照中的设备定义和已接受参数。</p>`,
    data=>{
      const end=numeric(data.duration,0,604800);
      if(end<=time)throw Error(`终止时刻必须晚于快照时刻 ${number(time,3)} s。`);
      msg('正在恢复会话快照…');
      engine.resumeArchive(id,end).then(()=>msg('已恢复到独立项目；使用单步或继续推进运行。')).catch(error=>msg(error.message,true));
    },'恢复并暂停');
}
function log(text,kind='INFO'){state.messages.unshift({time:new Date().toLocaleTimeString('zh-CN',{hour12:false}),kind,text});state.messages=state.messages.slice(0,80);}
function isCouplingChart(binding) {
  return Boolean(binding.couplingId||binding.couplingTotal||binding.canonicalKey?.startsWith('coupling.')||binding.canonicalKey?.startsWith('metrics.coupling_'));
}
function canvasEditSnapshot(owner=project()) {
  return projectState.canvasSnapshot(owner,state.charts.extra,ui);
}
function remember(){undoStack.push(canvasEditSnapshot());if(undoStack.length>30)undoStack.shift();redoStack=[];}
function undo(redo=false) {
  const from=redo?redoStack:undoStack,to=redo?undoStack:redoStack;if(!from.length)return;
  const owner=project(),next=from.at(-1),canvasEditSnapshotFromCurrent=canvasEditSnapshot(owner);
  // Restoring a canvas can also remove or restore a coupling endpoint. A live run
  // owns its original topology, including when paused.
  if(owner.thermalCouplings?.length||next.thermalCouplings?.length)coldStorage.assertCouplingIdle(owner);
  const restoredCharts=projectState.restoreCanvas(owner,next,state.charts.extra);
  to.push(canvasEditSnapshotFromCurrent);from.pop();state.charts.extra=restoredCharts;
  ui.workbenchChart=next.workbenchChart;ui.showChart=next.showChart;
  ui.selectedNode='';ui.selectedEdge='';ui.connecting=null;ui.pinnedChart=null;
  ui.floats=ui.floats.filter(f=>instance(f.id));markDirty(owner);persistLocal();render();msg(redo?'已重做':'已撤销');
}
function navigate(route,options={}){if(!PAGE_META[route])route='home';if(ui.route!==route)moduleReplay?.navigationChanged();if(ui.route!==route)ui.pinnedChart=null;Object.assign(ui,options);ui.route=route;contextMenu=null;ui.taskDrawer=false;if(location.hash!==`#${route}`)history.replaceState(null,'',`#${route}`);saveUI();render();page.scrollTop=0;if(route==='runs')engine.refreshArchives();}
function openProject(id){if(!state.projects.some(p=>p.id===id))return;state.activeProject=id;ui.pinnedChart=null;ui.chartCursor=null;ui.selectedNode='';ui.floats=[];undoStack=[];redoStack=[];navigate('workbench');}
function openEditor(id,tab='drawing',origin=null){ui.editorOrigin=origin;state.selectedModule=id;ui.editorPort='';ui.moduleTab=['design','header'].includes(tab)?'code':tab;if(['design','header'].includes(tab))ui.codeKind=tab;ui.arrayVar='system:form';navigate('editor');}
function heading(title,subtitle,actions='',eyebrow=''){return `<div class="page-heading"><div>${eyebrow?`<div class="eyebrow">${eyebrow}</div>`:''}<h1>${title}</h1><p>${subtitle}</p></div><div class="row wrap">${actions}</div></div>`;}
function renderHeader(){document.getElementById('app-header').innerHTML=`<button class="brand" data-action="nav" data-route="home" aria-label="FluidNet Studio 首页"><span class="brand-mark">${icon('Network')}</span>FluidNet <span class="brand-sub">Studio</span></button><span class="header-rule"></span><button class="project-picker" data-action="project-picker">${icon('FolderOpen')}<span>${esc(project().name)}</span>${icon('ChevronDown')}</button>${badge(engine?.health ? '模块平台 · v' + engine.health.version : '连接计算服务…',engine?.health ? 'good' : 'warn')}<button class="header-search" data-action="page-map" aria-label="页面导航与快捷入口">${icon('Search')}<span>页面与操作</span><kbd>Ctrl K</kbd></button><span class="save-indicator" data-save-status></span>${btn('workspace-tools','备份与恢复','Database')+btn('reload-workspace','载入服务器','FolderOpen','title="载入服务器工作区，当前草稿会先备份到浏览器"')+btn('save','<span>保存原型</span>','Save','title="保存全部项目、模块、型号和界面状态；待应用参数仍需单独应用"','header-save')}${ibtn('theme',ui.theme==='dark'?'切换浅色':'切换深色',ui.theme==='dark'?'Sun':'Moon')}${ibtn('nav','使用指南','CircleHelp','data-route="help"')}`;}
function renderRail(){const ids=['home','projects','workbench','modules','bench','models','curves','runs','air','batches','controls','connections'];document.getElementById('app-rail').innerHTML=ids.map(id=>`${id==='modules'||id==='controls'?'<div class="rail-divider"></div>':''}<button type="button" class="rail-link${ui.route===id||ui.route==='editor'&&id==='modules'||ui.route==='nodes'&&id==='modules'?' active':''}" data-action="nav" data-route="${id}" title="${PAGE_META[id][2]}"${ui.route===id?' aria-current="page"':''}>${icon(PAGE_META[id][1])}<span>${PAGE_META[id][0]}</span></button>`).join('')+`<div class="rail-bottom"><div class="rail-divider"></div><button class="rail-link${ui.route==='settings'?' active':''}" data-action="nav" data-route="settings">${icon('Settings2')}<span>设置</span></button></div>`;}
function syncChrome(){
  const projectName=root.querySelector('.project-picker > span');if(projectName)projectName.textContent=project().name;
  const save=root.querySelector('[data-save-status]');if(save){save.title=localSaveError||saveError||'';save.classList.toggle('dirty',state.dirty||!!localSaveError);save.innerHTML=`<span class="dot"></span>${localSaveError?'本地草稿保存失败 · 请导出原型':savePhase==='saving'?'正在保存…':savePhase==='error'?'保存失败 · 可重试':state.dirty?'有未保存修改':localSaveTrimmed?'草稿已保存 · 结果按需载入':state.savedAt?'工作区已保存':'示例已就绪'}`;}
  const run=project().run;const active=state.projects.filter(p=>p.run.status==='running'||p.run.status==='paused');
  document.getElementById('statusbar').innerHTML=`<span class="row gap-6"><span class="dot" style="color:var(--${run.status==='running'?'green':'muted'})"></span>${esc(project().name)} · ${statusText(run)}</span><span class="mono" data-live-time>${clockLabel(run.time)}</span>${active.length?`<button class="task-chip" data-action="tasks">${icon('Activity')} ${active.length} 个运行任务</button>`:''}<span class="optional">${currentProjectPending()?`当前项目 ${currentProjectPending()} 项待应用`:'当前项目参数已生效'}</span><span class="push"></span><button data-action="page-map" class="optional">页面导览</button><span class="prototype-label">单相流体网络 · Python 控制</span>`;syncWorkbenchStatus();
}
function render(){root.dataset.theme=ui.theme;renderHeader();renderRail();const views={home:renderHome,projects:renderProjects,workbench:renderWorkbench,modules:renderModules,bench:renderBench,editor:renderEditor,nodes:renderNodesPage,models:renderModels,curves:renderCurves,runs:renderRuns,air:()=>airSide.markup(project()),batches:()=>scenarioBatches.markup(project()),controls:renderControls,connections:renderConnections,settings:renderSettings,help:renderHelp};page.innerHTML=(views[ui.route]||renderHome)();renderFloats();syncChrome();renderDialog(false);requestAnimationFrame(()=>{resizeCharts();restoreChartCursor();if(ui.route==='connections'&&ui.connectionTab==='api')apiPreview();});if(recovery){msg(recovery,true);recovery='';}scenarioBatches.afterRender();airSide.afterRender();}
function thumbnail(p){return `<svg viewBox="0 0 1100 470" role="img" aria-label="${esc(p.name)}管网预览">${networkMarkup(p.pages[0],true)}</svg>`;}
function projectCard(p){return `<article class="project-card"><button class="project-preview" data-action="open-project" data-id="${p.id}" aria-label="打开 ${esc(p.name)}">${thumbnail(p)}${badge(p.id===state.activeProject?'当前项目':'示例','')}</button><div class="project-info"><h3>${esc(p.name)}</h3><div class="meta"><span>${p.pages.length} 张画布</span><span>·</span><span>${p.pages.reduce((s,c)=>s+c.nodes.length,0)} 个设备</span><span>·</span><span>${p.caseId==='cold-room-ideal-v1'?'库房热系统':esc(fluidBadge(p))}</span></div><div class="row spread"><small class="muted">${p.dirty?'草稿有修改':esc(p.modified||'示例项目')}</small><div class="row gap-6">${workflows.projectActions(p)}${ibtn('duplicate-project','复制项目','Copy',`data-id="${p.id}"`)}${btn('open-project','打开','ArrowUpRight',`data-id="${p.id}"`,'small')}</div></div></div></article>`;}
function renderHome(){return `<div class="page-shell">${heading('工作从这里开始','继续建模，或从一个验证过操作流程的示例开始。',btn('import','导入原型','Upload')+btn('new-project','新建项目','Plus','','primary'),'FLUIDNET WORKSPACE')}${entryPathsMarkup()}<div class="home-main"><div class="stack gap-20"><section><div class="section-title"><h2>最近项目</h2>${btn('nav','全部项目','ChevronRight','data-route="projects"','ghost small')}</div><div class="project-grid">${state.projects.slice(0,3).map(projectCard).join('')}</div></section><section class="panel"><div class="panel-head"><h2>最近使用的模块</h2>${btn('nav','模块库','ArrowUpRight','data-route="modules"','ghost small')}</div>${['valve','pump','exchanger','tank'].map(id=>{const m=mod(id);return `<div class="list-row"><span class="object-icon">${icon(m.icon)}</span><div class="grow"><strong>${m.name}</strong><small>${m.code} · ${m.ports.length} 个端口 · ${m.channels.length} 条内部通路</small></div>${badge('v'+m.version)}${btn('edit-module','编辑定义','Pencil',`data-id="${id}"`,'ghost small')}</div>`;}).join('')}</section></div><aside class="home-aside stack"><section class="panel"><div class="panel-head"><h2>快捷入口</h2>${icon('Grid2X2')}</div><div class="quick-list">${[['new-module','新建算法模块','Box'],['nav','管理设备型号','Database','models'],['nav','查看运行记录','History','runs'],['nav','页面与使用指南','BookOpen','help']].map(([act,label,i,r])=>`<button data-action="${act}" ${r?`data-route="${r}"`:''}>${icon(i)}<span class="grow">${label}</span>${icon('ChevronRight')}</button>`).join('')}</div></section><section class="panel"><div class="panel-head"><h2>消息与任务</h2>${badge('本地原型')}</div><div class="timeline">${state.messages.slice(0,3).map(m=>`<div class="timeline-item"><span class="timeline-point">${icon('CheckCircle2')}</span><div>${esc(m.text)}<small>${m.time} · ${m.kind}</small></div></div>`).join('')}</div></section><section class="panel"><div class="panel-body stack"><div class="row">${icon('Info')}<strong>当前体验范围</strong></div><p class="muted" style="font-size:12px">主系统运行已接入真实水力与热力求解。含水箱或管道热容分段的项目按隐式 Euler 积分液位、水温与管内温度，其余动态为准稳态时间序列。动态运行是可暂停、单步和运行中改参数的会话；「控制」页可配置 PID（Lua 控制脚本尚未接入）。Python 模块支持独立验证与版本保存。</p>${btn('page-map','查看全部页面','LayoutDashboard','','small')}</div></section></aside></div></div>`;}
function renderProjects(){let list=state.projects.filter(p=>(p.name+p.description).toLowerCase().includes(ui.projectSearch.toLowerCase()));if(ui.projectFilter==='current')list=list.filter(p=>p.id===state.activeProject);return `<div class="page-shell">${heading('项目管理','按项目保存、导入导出与恢复修订；运行记录独立保存。',workflows.projectToolbar()+btn('cs-create-continuous','六库持续仿真','Activity')+btn('cs-create-multi','六库自动温控','Snowflake')+btn('cs-create','−18°C 冷库案例','Thermometer')+btn('cs-create-station','NH₃/CO₂ 冷库案例','Wind')+btn('cs-create-coupled','制冷站热耦合','ArrowRightLeft')+btn('cs-create-dual','双盘管示例','Network')+btn('import','导入原型','Upload')+btn('new-project','新建项目','Plus','','primary'))}<div class="filterbar"><label class="search">${icon('Search')}<input aria-label="搜索项目" data-filter="projectSearch" placeholder="搜索项目名称" value="${esc(ui.projectSearch)}"></label><div class="segmented">${[['all','全部项目'],['current','当前项目']].map(([k,v])=>`<button data-action="project-filter" data-value="${k}" class="${ui.projectFilter===k?'active':''}">${v}</button>`).join('')}</div><span class="push"></span><span class="muted">${list.length} 个项目</span><div class="segmented">${['grid','list'].map(k=>`<button aria-label="${k==='grid'?'卡片视图':'列表视图'}" data-action="project-view" data-value="${k}" class="${ui.projectView===k?'active':''}">${icon(k==='grid'?'Grid2X2':'List')}</button>`).join('')}</div></div><div id="project-results" class="project-grid${ui.projectView==='list'?' project-list-view':''}">${list.map(projectCard).join('')||empty('没有匹配的项目','换个关键词，或新建一个项目。')}</div><div class="home-note"><span class="note-icon">${icon('Folder')}</span><div class="grow"><strong>项目与修订保存在服务器工作区</strong><p>“管理”可单独保存项目、导出及恢复修订；“保存原型”保存完整工作区。</p></div>${btn('export','导出原型','Download','data-format="prototype"','ghost')}</div></div>`;}
let engineeringCanvas;
function canvasView(){return engineeringCanvas ||= FluidNetCanvasWorkspace.create({getState:()=>state,project,activePage,moduleOf,ui,esc,btn,links,domains:DOMAINS,quick:quickCanvasMarkup,channels:internalChannelsMarkup,projectKey:projectParameterKey,selectedIds:groupSelected,engine:()=>engine,openDialog,closeDialog,render,saveUI,
  locate:id=>{const found=links.locate(project(),id);if(!found)throw Error('设备已不存在');project().activePage=found.page.id;ui.selectedNode=id;fitNetwork(found.page);render();openDevice(id);}});}
function portOffset(n,p){return FluidNetCanvasSymbols.portOffset(n,moduleOf(n),p);}
function portHitRadius(n,p){return FluidNetCanvasSymbols.hitRadius(n,moduleOf(n),p);}
function endpoint(pg,nodeId,portId){return canvasView().endpoint(pg,nodeId,portId);}
function globalEndpoint(owner,nodeId,portId){const found=links.locate(owner,nodeId);return found?endpoint(found.page,nodeId,portId):null;}
function pageLinkStrip(pg){
  const entries=links.cross(project(),pg.id);
  if(!entries.length)return '';
  return `<div class="cross-page-strip" aria-label="当前画布跨页连接">${entries.map(link=>`<button type="button" data-action="jump-page-link" data-id="${esc(link.edge[0])}" data-node="${esc(link.remote[0])}" title="跳转到 ${esc(link.remotePage.name)} · ${esc(link.remote.join(':'))}">${icon('ArrowRightLeft')}<span>${esc(link.local.join(':'))} ↔ ${esc(link.remotePage.name)} · ${esc(link.remote.join(':'))}</span>${icon('ArrowUpRight')}</button>`).join('')}</div>`;
}
// Live readouts prefer the latest full response; old runs fall back to complete history rows.
function panelRow(run){return projectRunState.completeRow(run)||run?.history?.at(-1);}
function replayingKeyFrame(run){const last=run?.history?.at(-1),row=projectRunState.completeRow(run);return !!last?.partial&&(!row||row.t<last.t);}
const CIRCUIT_COLORS=['var(--orange)','#2f80ed','#27ae60','#9b51e0','#eb5757','#f2994a','#219653','#56ccf2'];
function networkMarkup(pg,mini=false){return canvasView().markup(pg,mini);}
function fluidBadge(p){const circuits=engine.circuits?.(p.id)||[];if(new Set(circuits.map(c=>c.fluid.fluid)).size>1)return `多工质 · ${circuits.length} 个回路`;const declared=new Set((p.circuitFluids||[]).map(c=>c.fluid||c.medium).filter(Boolean));if(!circuits.length&&declared.size>1)return `多工质 · ${[...declared].join(' / ')}`;return p.fluid||(MEDIA.find(m=>m[0]===p.medium)||MEDIA[0])[1];}
function renderWorkbench(){const p=project(),pg=activePage(),selected=instance(ui.selectedNode);return `<div class="workbench${ui.showLibrary?' show-library':''}${ui.showChart?' with-chart':''}"><aside class="canvas-library" id="canvas-library"><div class="library-heading"><strong>模块库</strong><small class="muted">${state.modules.length} 类</small>${ibtn('toggle-library','关闭模块库','PanelLeftClose')}</div><label class="search">${icon('Search')}<input placeholder="查找模块" aria-label="画布模块搜索" data-filter="canvasModuleSearch"></label><div class="library-scroll" id="canvas-library-list">${libraryMarkup()}</div><div class="selected-properties" id="selected-properties">${propertiesMarkup(selected)}</div></aside><div class="canvas-column"><div class="canvas-bar"><div class="canvas-pages">${pgTabs()}${ibtn('new-canvas','新增画布','Plus')}</div><div class="canvas-tools">${workflows.scenarioToolbar(p)}${coldStorage.couplingToolbar(p)}${coldStorage.assemblyToolbar(p)}${ibtn('toggle-library',ui.showLibrary?'收起模块库':'展开模块库',ui.showLibrary?'PanelLeftClose':'PanelLeftOpen',`aria-expanded="${ui.showLibrary}" aria-controls="canvas-library"`)}${ibtn('select-mode','选择设备','MousePointer2')}${ibtn('project-group-tools','多选与设备组操作','Boxes')}${ibtn('project-find','全项目查找','Search')}${ibtn('device-batch-edit','批量编辑设备','SlidersHorizontal')}${ibtn('connect-mode','连接端口','Cable')}${ibtn('page-links','跨页连接','ArrowRightLeft')}<span class="tool-divider"></span>${ibtn('undo','撤销 Ctrl+Z','Undo2',undoStack.length?'':'disabled')}${ibtn('redo','重做 Ctrl+Y','Redo2',redoStack.length?'':'disabled')}${ibtn('fit','适应画布','Scan')}${ibtn('grid','显示点阵','Grid2X2','class="optional"')}${ibtn('validate','检查连接','ListChecks')}</div></div>${pageLinkStrip(pg)}${canvasView().tools()}<div id="canvas-device-tools">${deviceToolsMarkup(selected)}</div><div class="canvas-area${ui.pageGrid?' grid':''}" id="network-area"><div class="canvas-caption"><span>${esc(pg.name)}</span><span class="muted">${p.caseId==='cold-room-ideal-v1'?'库房热平衡 · W':p.run.history.length?'真实采样 · 结果图例见上方':'单击选择 · 双击参数'}</span>${badge(p.caseId==='cold-room-ideal-v1'?'传热系统':fluidBadge(p),'blue')}</div>${pg.nodes.length?`<svg id="network" data-project="${esc(p.id)}" data-page="${esc(pg.id)}" class="network-svg" viewBox="${networkViewBox(pg)}" role="group" aria-label="${esc(p.name+' '+pg.name+' 管网画布')}">${networkMarkup(pg)}</svg>`:`<div class="empty" style="padding-top:18%">${icon('Network')}<h3>在这里搭建新系统</h3><p>从左侧选择模块，再点击画布放置设备。</p>${p.modelingDomain==='refrigeration'?btn('cs-assembly-guide','查看设备与连接说明','ListChecks','','primary'):btn('insert-defaults','放入泵阀示例','Plus','','primary')}</div><svg id="network" data-project="${esc(p.id)}" data-page="${esc(pg.id)}" class="network-svg" viewBox="-35 -5 1140 510" style="position:absolute;inset:0" aria-label="空画布"></svg>`}<div class="runbar" aria-label="主系统运行控制"><button data-action="run-project" data-command="run" class="go" ${['running','solving'].includes(p.run.status)?'disabled':''}>${icon('Play')}<span>${p.run.status==='paused'?'继续':'运行'}</span></button><button data-action="run-project" data-command="pause" ${p.run.status==='running'?'':'disabled'}>${icon('Pause')}暂停</button><button data-action="run-project" data-command="step" ${['running','solving'].includes(p.run.status)?'disabled':''}>${icon('StepForward')}单步</button><button data-action="run-project" data-command="stop" ${['ready','stopped'].includes(p.run.status)?'disabled':''}>${icon('Square')}停止</button><span class="spacer"></span><button data-action="toggle-chart" aria-label="${ui.showChart?'收起同屏曲线':'展开同屏曲线'}" aria-expanded="${ui.showChart}" class="${ui.showChart?'active':''}">${icon('Activity')}曲线</button></div><div id="canvas-inspection" class="canvas-inspection" role="status" hidden></div><div class="canvas-bottom"><span data-canvas-hint>${ui.placing?'点击画布放置 '+mod(ui.placing).name:ui.connecting?'可切换画布选择另一个空闲端口 · Esc 取消':'双击设备编辑参数 · 拖动空白处平移'}</span><div class="zoom">${ibtn('zoom-out','缩小','Minus')}<span>${Math.round(pg.zoom*100)}%</span>${ibtn('zoom-in','放大','Plus')}</div></div></div>${renderWorkbenchChart()}${coldStorage.markup(p)}<div class="canvas-info"><span data-result-status></span><span class="optional">${pg.nodes.length} 个设备 · ${pg.edges.length} 条连接</span><span class="push"></span>${btn('nav','项目设置','Settings2','data-route="settings"','ghost small')}${btn('nav','控制逻辑','Code2','data-route="controls"','ghost small')}</div></div><aside id="inspector-dock" aria-hidden="true"></aside></div>`;}
function pgTabs(){return project().pages.map(p=>`<button data-action="canvas-tab" data-id="${p.id}" class="${p.id===project().activePage?'active':''}">${esc(p.name)}</button>`).join('');}
function libraryMarkup(query=''){return moduleGroupNames().map(c=>{const modules=state.modules.filter(m=>m.category===c&&(m.name+m.code).toLowerCase().includes(query.toLowerCase()));return modules.length?`<div class="library-caption">${icon('ChevronDown')}${esc(c)}</div>${modules.map(m=>`<button class="library-item${ui.placing===m.id?' active':''}" data-action="place-module" data-id="${m.id}" draggable="true" data-drag-module="${m.id}">${icon(m.icon)}<span>${m.name}</span><small>${m.runtime === 'python' ? 'Python' : m.code.slice(0,2)}</small></button>`).join('')}`:'';}).join('');}
function propertiesMarkup(n){if(n){const m=moduleOf(n);return `<div class="row spread"><h3>对象属性</h3>${badge(n.id,'warn')}</div><dl><dt>名称</dt><dd>${esc(n.name)}</dd><dt>模块</dt><dd>${esc(m.name)}</dd>${m.runtime==='python'?`<dt>模块版本</dt><dd data-module-binding>v${m.version} · ${esc((m.manifest.definition_hash || m.contentHash).slice(0,12))}</dd>`:''}<dt>型号</dt><dd>${esc(model(n.modelId)?.name||'自定义参数')}</dd>${paramDefs(n).slice(0,2).map(f=>`<dt>${f[1].replace('阀门','').replace('流量系数 ','')}</dt><dd>${number(n.params[f[0]],f[0]==='opening'?0:2)} ${f[2]}</dd>`).join('')}</dl><div class="row gap-6">${btn('open-device','详细参数','SlidersHorizontal',`data-id="${n.id}"`,'small')}${ibtn('delete-node','删除选中设备','Trash2',`data-id="${n.id}"`)}</div>`;}return `<h3>画布属性</h3><dl><dt>画布</dt><dd>${esc(activePage().name)}</dd><dt>介质</dt><dd>${esc(fluidBadge(project()))}</dd><dt>选择</dt><dd>${ui.selectedEdge?'已选连接 '+esc(ui.selectedEdge):'单击设备或连接'}</dd></dl>${ui.selectedEdge?btn('delete-edge','删除连接','Trash2',`data-id="${ui.selectedEdge}"`,'small'):btn('nav','管理模块','Boxes','data-route="modules"','small ghost')}`;}
function channelFor(m,v){return m.channels.find(c=>c.enabled&&(c.input===v.port||c.output===v.port));}
let moduleEditorPresentation,runResultsPresentation;
function moduleEditorView(){return moduleEditorPresentation ||= FluidNetModuleEditorView.create({
  currentModule:mod,editorState:()=>ui,models:()=>state.models,parameterDefinitions:kind=>PARAM_DEFS[kind],builtinDefinition:m=>engine.catalog?.modules.find(d=>d.id===m.kind),contractText:m=>engine.contractText(m),
  chrome:{esc,icon,btn,ibtn,badge,option,number},constants:{DOMAINS,PORT_PREFIX,FLUIDS,EDITOR_TABS,PARAM_TYPE_LABELS},
  actions:{selectTab:value=>{ui.moduleTab=value;saveUI();render();},selectPort:id=>{ui.editorPort=id;render();},editLabel:()=>{ui.editorPort='picture';render();root.querySelector('[data-drawing-field="label"]')?.focus();}}
});}
function runResultsView(){return runResultsPresentation ||= FluidNetRunResultsView.create({
  currentRun:currentChartRun,currentProject:project,records:()=>state.records,chartState:()=>state.charts,viewState:()=>ui,overviewSeries,
  chartBindings:chartBindingsForRun,extraValue:extraVariableValue,series:SERIES,registerChart:(id,data)=>chartRegistry.set(id,data),
  measureWidth:id=>document.getElementById(id)?.getBoundingClientRect().width||(ui.route==='bench'?page.clientWidth-390:page.clientWidth-125),
  comparisonMarkup:()=>workflows.comparisonMarkup(),reportAvailable:record=>engine.refrigerationReportAvailable(record),runControls,
  chrome:{esc,icon,btn,ibtn,badge,option,number,heading,clockLabel},actions:{
    selectRecord:id=>{ui.selectedRecord=id;render();},recordCurves:async id=>{
      try{if(state.records.find(r=>r.id===id)?.archiveCacheOnly)await engine.openArchive(id);
        state.charts.source=id;navigate('curves');}catch(error){msg('完整曲线暂时无法读取：'+error.message,true);}},
    toggleSeries:key=>{ui.pinnedChart=null;state.charts.series[key]=!state.charts.series[key];markDirty();render();},
    removeVariable:id=>{state.charts.extra=state.charts.extra.filter(v=>v.id!==id||v.projectId!==project().id);markDirty();render();}}
});}
function renderEditor(...args){return moduleEditorView().renderEditor(...args);}
function drawingSVG(...args){return moduleEditorView().drawingSVG(...args);}
function renderDrawing(...args){return moduleEditorView().renderDrawing(...args);}
function variableRows(...args){return moduleEditorView().variableRows(...args);}
function renderAttributes(...args){return moduleEditorView().renderAttributes(...args);}
function valueTable(...args){return moduleEditorView().valueTable(...args);}
function bankDiff(...args){return moduleEditorView().bankDiff(...args);}
function renderValues(...args){return moduleEditorView().renderValues(...args);}
function renderEditorModels(...args){return moduleEditorView().renderEditorModels(...args);}
function renderCodePane(...args){return moduleEditorView().renderCodePane(...args);}
function renderDesignSourcePane(...args){return moduleEditorView().renderDesignSourcePane(...args);}
async function runDesign(bank = ui.bank) {
  const m = mod();
  if (m.runtime !== 'python') { previewDesign(bank); return; }
  if (!m.designSource?.trim()) { msg('此模块还没有 design.py，请先在“算法”页编写设计函数。', true); return; }
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
function renderPythonAttributes(...args){return moduleEditorView().renderPythonAttributes(...args);}
function editModuleMetadata() {
  const m=mod(),workspace=state;
  openDialog('设备名称与说明','名称用于模块库和新放入的设备。说明可以写用途、连接方式和常用调节项。',
    `<div class="stack">${field('name','设备名称',m.name,'required maxlength="80"')}<label class="field"><span>用途与使用说明</span><textarea name="description" rows="4" maxlength="4000">${esc(m.description||'')}</textarea></label><small class="muted">模块标识：${esc(m.id)}</small></div>`,data=>{
      if(state!==workspace||mod()!==m)throw Error('当前模块已切换，请重新打开。');
      engine.updateMetadata(m,data);
    },'应用到草稿');
}
function editModuleParameter(id) {
  const m=mod(),workspace=state,{spec,units}=engine.parameterEditor(m,id),before=JSON.stringify(engine.manifestPayload(m));
  if(spec.value_type==='curve'){if(FluidNetPumpCurveEditor.supported(m,spec))editPumpCurve(null,id);else editContractItem('parameters',id);return;}
  const display=value=>value==null?'':projectModel.toDisplay(spec,value);
  openDialog(id?'编辑常用参数':'新增参数','按所选单位填写默认值和范围，保存模块版本后用于新设备。',
    `<div class="stack"><div class="fields">${field('label','参数名称',spec.label,'required maxlength="80"')}${id?`<label class="field"><span>参数标识</span><input value="${esc(id)}" readonly></label>`:field('id','参数标识','','required pattern="[A-Za-z][A-Za-z0-9_-]*" maxlength="81"')}${id?'':selectField('value_type','参数类型',[['number','数值'],['boolean','是／否'],['text','文本']],'number')}</div><div id="simple-parameter-fields"></div><p class="muted">${id?spec.runtime?'此参数允许运行中调整。':spec.writable===false?'此参数在项目中只读。':'此参数可在运行前调整。':'新增参数默认允许在运行前调整。'}</p></div>`,data=>{
      if(state!==workspace||mod()!==m||before!==JSON.stringify(engine.manifestPayload(m)))throw Error('模块已变化，请重新打开参数编辑。');
      engine.updateDisplayParameter(m,id,data);
    },'应用到草稿');
  const form=document.getElementById('dialog-form');let unit=spec.unit;
  function renderFields(){
    const type=id?spec.value_type:form.elements.value_type.value;
    form.querySelector('#simple-parameter-fields').innerHTML=type==='number'?`<div class="fields">${selectField('unit','显示单位',units.map((u,index)=>[index,u?.display_unit||'无单位']),0)}${field('default','默认值',display(spec.default),'type="number" step="any" required')}${field('minimum','最小值（可留空）',display(spec.minimum),'type="number" step="any"')}${field('maximum','最大值（可留空）',display(spec.maximum),'type="number" step="any"')}</div><small class="muted">切换单位会换算已填写的数值，保留实际大小。</small>`:
      type==='boolean'?selectField('default','默认值',[['true','是'],['false','否']],String(typeof spec.default==='boolean'?spec.default:false)):
      field('default','默认文本',typeof spec.default==='string'?spec.default:'','maxlength="4000"');
    unit=spec.unit;
    form.elements.unit?.addEventListener('change',()=>{
      const next=units[Number(form.elements.unit.value)];
      for(const key of ['default','minimum','maximum']){
        const input=form.elements[key];if(input.value==='')continue;
        const canonical=projectModel.toCanonical({...spec,unit},Number(input.value));
        const converted=projectModel.toDisplay({...spec,unit:next},canonical);
        if(Number.isFinite(converted))input.value=Number(converted.toPrecision(14));
      }
      unit=next;
    });
  }
  form.addEventListener('input',()=>{form.querySelector('#dialog-error').hidden=true;});
  form.elements.value_type?.addEventListener('change',renderFields);renderFields();
}
function editPumpCurve(nodeId,parameterId='head_curve',readonly=false){
  const workspace=state,n=nodeId?instance(nodeId):null,owner=n?ownerOfInstance(n):null,m=n?moduleOf(n):mod();
  if(nodeId&&!n)throw Error('设备已不存在，请重新打开。');
  const spec=n?deviceParamSpecs(n).find(p=>p.id===parameterId):engine.manifestPayload(m).parameters.find(p=>p.id===parameterId);
  if(!FluidNetPumpCurveEditor.supported(m,spec))throw Error('此参数没有可用的泵曲线点表。');
  const initial=clone(n?(n.draft[parameterId]??n.params[parameterId]??spec.default):spec.default);
  const current=JSON.stringify(n?n.draft[parameterId]:engine.manifestPayload(m));
  function check(){
    if(state!==workspace)throw Error('工作区已切换，请重新打开曲线编辑。');
    if(n){
      projectState.assertCurrent(state,owner);projectState.node(owner,n);
      if(moduleOf(n)!==m||JSON.stringify(n.draft[parameterId])!==current)throw Error('设备或曲线草稿已变化，请重新打开。');
      if(readonly||spec.writable===false)throw Error('此曲线为只读。');
      if(owner.run.live||['running','solving','paused'].includes(owner.run.status))throw Error('请先停止运行，再编辑泵曲线。');
    }else if(mod()!==m||current!==JSON.stringify(engine.manifestPayload(m)))throw Error('模块已变化，请重新打开曲线编辑。');
  }
  check();let editor;
  openDialog('泵曲线点表',`${n?n.name:m.name} · 首点流量为 0；流量递增、扬程递减；末点扬程为 0。`,
    '<div id="pump-curve-editor"></div>',()=>{
      check();const points=editor.read();
      if(n){projectState.setDraft(owner,n,{[parameterId]:points});markDirty(owner);render();msg('曲线已保存为设备草稿，点击“预览并应用”后生效。');}
      else engine.updateContractItem(m,'parameters',parameterId,{...spec,default:points},true);
    },n?'保存为设备草稿':'保存为模块草稿',true);
  const form=document.getElementById('dialog-form');
  editor=FluidNetPumpCurveEditor.mount(form.querySelector('#pump-curve-editor'),initial,{esc,onValidity:valid=>form.querySelector('[type="submit"]').disabled=!valid});
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
function renderModuleContract(...args){return moduleEditorView().renderModuleContract(...args);}
function renderCode(...args){return moduleEditorView().renderCode(...args);}
function renderAuthoringDiagnostics(...args){return moduleEditorView().renderAuthoringDiagnostics(...args);}
function configureAuthoringSuite(m) {
  const definition=engine.manifestPayload(m);
  let editor;
  openDialog('模块测试组合','为每个工况设置边界、参数和结果预期。配置随工作区保存。', '<div id="module-suite-editor"></div>',()=>{
    m.authoringTestCases=editor.read();m.authoringOutput='测试配置已更新，请运行测试组合。';m.authoringDiagnostics=[];
    markDirty();render();
  },'保存测试配置',true);
  editor=ModuleTestEditor.mount(document.getElementById('module-suite-editor'),ModuleTestEditor.cases(m,definition),definition);
}
function moduleEvidenceSummary(...args){return moduleEditorView().moduleEvidenceSummary(...args);}
async function runAuthoringSuite(m) {
  ui.moduleSuiteAbort?.abort();
  const controller=new AbortController(); ui.moduleSuiteAbort=controller;
  const definition=engine.manifestPayload(m), before=JSON.stringify(definition);
  const cases=ModuleTestEditor.cases(m,definition), casesBefore=JSON.stringify(cases);
  m.authoringOutput=`正在执行 ${cases.length} 个工况及预期值检查…`;render();
  try {
    const response=await fetch('/api/v1/modules/test-suite',{method:'POST',headers:{'Content-Type':'application/json',...engine.authHeaders()},body:JSON.stringify({module:definition,cases}),signal:controller.signal});
    const data=await response.json(); if(!response.ok)throw Error(data.detail?.message || JSON.stringify(data.detail));
    if(before!==JSON.stringify(engine.manifestPayload(m)) || casesBefore!==JSON.stringify(ModuleTestEditor.cases(m,definition)))throw Error('测试期间草稿或测试配置已变化，请重新验证。');
    m.authoringDiagnostics=data.cases.flatMap(c=>c.diagnostics);
    m.authoringOutput=ModuleTestEditor.summary(data);
  } catch(error){m.authoringOutput=error.name==='AbortError'?'测试已取消，草稿已保留。':'测试失败：'+error.message;}
  finally{if(ui.moduleSuiteAbort===controller){ui.moduleSuiteAbort=null;render();}}
}
function renderChannels(...args){return moduleEditorView().renderChannels(...args);}
function renderNodesPage(){const domain=DOMAINS[ui.nodeDomain];return `<div class="page-shell">${heading('节点与端口定义','按物理类型组织接口，明确变量含义与连接规则。',btn('nav','返回模块库','ChevronLeft','data-route="modules"'))}<div class="split-view"><aside class="side-nav"><div class="side-caption">接口领域</div>${Object.entries(DOMAINS).map(([k,d])=>`<button data-action="node-domain" data-value="${k}" class="${k===ui.nodeDomain?'active':''}">${icon(d.icon)}${d.label}端口</button>`).join('')}</aside><div class="stack"><section class="panel"><div class="panel-head"><div class="row"><span class="object-icon">${icon(domain.icon)}</span><div><h2>${domain.label}端口</h2><small class="muted">${ui.nodeDomain==='fluid'?'状态量、流量与工质组成':'接口与变量定义示例'}</small></div></div>${badge(ui.nodeDomain==='fluid'?'液态水场景':'接口预留',ui.nodeDomain==='fluid'?'good':'warn')}</div><div class="table-wrap"><table><thead><tr><th>变量后缀</th><th>中文名称</th><th>单位</th><th>说明</th></tr></thead><tbody>${(ui.nodeDomain==='fluid'?[['FLOW','质量流量','kg/s','沿端口约定方向记录，可表达反向流动'],['PRE','绝对压力','MPa','与求解器约定之间显式换算'],['ENTHALPY','比焓','kJ/kg','能量输运状态量'],['TEMP','温度','°C','工程显示单位'],['VOLUME','密度','kg/m³','参考命名对应密度，不能当作比容'],['Q','干度','—','相态描述；当前水网范围不扩展两相求解'],['X','质量组分','—','与 FORM 工质顺序对应']]:ui.nodeDomain==='info'?[['VALUE','信号数值','自定义','根据物理量定义单位'],['QUALITY','数据质量','—','有效、过期或缺失状态']]:ui.nodeDomain==='power'?[['VOLTAGE','电压','V','电气接口的定义示例'],['CURRENT','电流','A','当前原型不提供电网计算']]:[['SPEED','转速','r/min','机械接口的定义示例'],['TORQUE','转矩','N·m','当前原型不提供机械求解']]).map(row=>`<tr>${row.map((v,i)=>`<td${i===0?' class="mono"':''}>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section><section class="panel"><div class="panel-head"><h3>连接规则</h3></div><div class="panel-body stack"><div class="row">${icon('CheckCircle2')}同一内部通路的两端类型一致</div><div class="row">${icon('CheckCircle2')}端口拥有稳定标识，显示名称可以独立编辑</div><div class="row">${icon('CheckCircle2')}一个项目端口对应一条连接，分支使用连接节点</div><div class="row">${icon('CheckCircle2')}类型与单位定义供变量表、图形、型号和曲线共用</div></div></section>${btn('edit-module','在模块中配置端口','ArrowRight',`data-id="${ui.nodeDomain==='fluid'?'valve':'pid'}"`,'primary')}</div></div></div>`;}
function renderModels(){let models=state.models.filter(m=>(ui.modelFilter==='archived'?m.archived:!m.archived)&&(m.name+mod(m.moduleId).name).toLowerCase().includes(ui.modelSearch.toLowerCase()));const selected=models.find(m=>m.id===state.selectedModel)||models[0];return `<div class="page-shell">${heading('设备型号库','从已验证的参数形成型号；项目实例保留自己的参数与来源版本。',btn('new-model','保存新型号','Plus','','primary'))}<div class="filterbar"><label class="search">${icon('Search')}<input data-filter="modelSearch" aria-label="搜索型号" placeholder="型号名称或模块名称" value="${esc(ui.modelSearch)}"></label><div class="segmented">${[['all','在用型号'],['archived','已归档']].map(([k,v])=>`<button data-action="model-filter" data-value="${k}" class="${ui.modelFilter===k?'active':''}">${v}</button>`).join('')}</div><span class="push muted">${models.length} 个型号</span>${btn('export','导出型号库','Download','data-format="models"','small')}</div><div class="model-layout"><section class="panel"><div class="table-wrap"><table><thead><tr><th>型号名称</th><th>所属模块</th><th>版本</th><th>主要参数</th><th></th></tr></thead><tbody>${models.map(m=>`<tr class="${m.id===selected?.id?'model-selected':''}"><td><button data-action="focus-model" data-id="${m.id}" style="text-align:left;padding:0"><strong>${esc(m.name)}</strong><small>${esc(m.description)}</small></button></td><td>${esc(mod(m.moduleId).name)}</td><td>${badge('v'+m.version)}</td><td>${Object.entries(m.params).slice(0,2).map(([k,v])=>`<span class="mono">${esc(typeof v==='object'?JSON.stringify(v):v)}</span> ${(PARAM_DEFS[mod(m.moduleId).kind]||[]).find(f=>f[0]===k)?.[2]||''}`).join(' · ')}</td><td>${ibtn('focus-model','查看型号 '+m.name,'ChevronRight',`data-id="${m.id}"`)}</td></tr>`).join('')||'<tr><td colspan="5">没有匹配的型号。</td></tr>'}</tbody></table></div></section>${selected?`<aside class="model-detail stack"><section class="panel"><div class="panel-head"><div><h2>${esc(selected.name)}</h2><small class="muted">${esc(mod(selected.moduleId).name)} · v${selected.version}</small></div>${icon('Database')}</div><div class="panel-body stack"><p class="muted" style="font-size:12px">${esc(selected.description)}</p><div class="fields">${Object.entries(selected.params).map(([key,val])=>{const f=(PARAM_DEFS[mod(selected.moduleId).kind]||[]).find(f=>f[0]===key),spec=mod(selected.moduleId).manifest?.parameters.find(p=>p.id===key);return `<div class="field"><span>${esc(f?.[1]||spec?.label||key)}</span><strong>${typeof val==='number'?number(val,f?.[0]==='opening'?0:2):esc(typeof val==='object'?JSON.stringify(val):String(val))} <small class="muted">${f?.[2]||''}</small></strong></div>`;}).join('')}</div>${modelVariableSummary(selected)}<div class="spacer"></div>${btn('insert-model','插入当前项目','Plus',`data-id="${selected.id}"`,'primary')}${btn('apply-model-to-instance','应用到已有设备','GitCompareArrows',`data-id="${selected.id}"`)}<div class="row">${btn('edit-model','保存新版本','Pencil',`data-id="${selected.id}"`,'small')}${btn('archive-model',selected.archived?'恢复型号':'归档型号','History',`data-id="${selected.id}"`,'ghost small')}</div><small class="muted">更新型号不会自动改动已插入的实例。</small></div></section><section class="panel"><div class="panel-head"><h3>版本记录</h3>${badge(selected.versions.length+' 个版本')}</div><div class="panel-body">${selected.versions.slice().reverse().map(v=>`<div class="version-item"><span class="object-icon" style="width:26px;height:26px">${icon('History')}</span><div class="grow"><strong>v${v.version}</strong><small>${esc(v.note)}</small></div>${v.version===selected.version?badge('当前'):btn('model-version','对照','','data-version="'+v.version+'" data-id="'+selected.id+'"','small')}</div>`).join('')}</div></section></aside>`:''}</div></div>`;}
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
function renderBench(){if(moduleReplay?.active)return moduleReplay.body();const b=state.bench,m=mod(b.moduleId),run=b.run,refrigeration=Boolean(m.manifest?.execution_role);if(m.manifest?.sdk?.capabilities?.includes('composite.refrigeration.open.v1'))return renderHostBench(b,m);return `<div class="page-shell">${heading('独立验证台','用独立边界与参数检查设备；测试不会改变项目实例。',btn('edit-module','编辑模块','Pencil',`data-id="${m.id}"`)+btn('save','保存测试配置','Save'))}<div class="bench-layout"><aside class="stack"><section class="panel"><div class="panel-head"><h3>被测设备</h3>${badge(m.runtime === 'python' ? 'Python Worker · v'+m.version : '请选择 Python 模块','blue')}</div><div class="panel-body stack"><label class="field"><span>模块</span><select data-bench-module aria-label="选择被测模块" ${['running','solving'].includes(run.status)?'disabled':''}>${state.modules.filter(x=>x.runtime === 'python').map(x=>option(x.id,x.name,m.id)).join('')}</select></label>${benchParamFields(m, b)}<small class="muted">参数仅用于此测试副本。</small></div></section><section class="panel"><div class="panel-head"><h3>边界条件</h3></div><div class="panel-body stack">${refrigeration ? `<p class="muted">${m.manifest?.schema_version===5 ? '入口为饱和蒸气状态；验证压缩机轴功和流股焓升，或冷凝器热流与温差方向。' : '入口为饱和液体，温度由压力确定；出口为给定压力的同焓流股。'}压力均为绝压。</p><label class="field"><span>制冷剂名称</span><input data-bench-fluid value="${esc(b.boundary.fluid || 'Ammonia')}" aria-label="测试制冷剂" ${['running','solving'].includes(run.status)?'disabled':''}></label>` : ''}${[['inlet','入口压力','kPa'],['outlet','出口压力','kPa'],...(!refrigeration ? [['temperature','入口温度','°C']] : [])].map(([key,label,unit])=>`<label class="field"><span>${label}</span><div class="field-unit"><input type="number" data-bench-boundary="${key}" step="any" value="${b.boundary[key]}" aria-label="测试${label}" ${['running','solving'].includes(run.status)?'disabled':''}><span>${unit}</span></div></label>`).join('')}<label class="field"><span>时间步长</span><div class="field-unit"><input type="number" data-bench-step ${['running','solving'].includes(run.status)?'disabled':''} value="${run.step}" min=".01" max="10" step=".01"><span>s</span></div></label></div></section></aside><section class="panel"><div class="run-control"><div class="runtime"><span class="dot" style="color:var(--green)"></span><strong>${m.name} · ${statusText(run)}</strong><span class="mono" data-bench-time>${clockLabel(run.time)}</span></div><span class="push"></span>${runControls('bench',run)}</div><div class="bench-schematic"><svg viewBox="0 0 780 180" role="img" aria-label="独立边界与被测设备"><path d="M 145 80 H 620" class="net-line"/><circle cx="145" cy="80" r="25" fill="var(--blue-soft)" stroke="var(--blue)"/><circle cx="620" cy="80" r="25" fill="var(--blue-soft)" stroke="var(--blue)"/><rect x="300" y="48" width="165" height="65" rx="7" fill="var(--surface)" stroke="var(--orange)"/><text x="382" y="84" text-anchor="middle" fill="var(--text)" font-size="15">${esc(m.name)}</text><text x="145" y="85" text-anchor="middle" fill="var(--blue)" font-size="14">P</text><text x="620" y="85" text-anchor="middle" fill="var(--blue)" font-size="14">P</text><text x="145" y="136" text-anchor="middle" fill="var(--muted)" font-size="12">${b.boundary.inlet} kPa</text><text x="620" y="136" text-anchor="middle" fill="var(--muted)" font-size="12">${b.boundary.outlet} kPa</text><text x="382" y="150" text-anchor="middle" fill="var(--muted)" font-size="11">${m.manifest?.schema_version===5 ? '饱和容器边界 · 作者本构与守恒校验' : refrigeration ? '饱和液体 → 等焓节流 → 定压出口' : '独立网络 · Worker 实际求解'}</text></svg></div><div class="tabs">${[['results','运行结果'],['curves','趋势曲线'],['events','事件记录']].map(([k,v])=>`<button data-action="bench-tab" data-value="${k}" class="${ui.benchTab===k?'active':''}">${v}</button>`).join('')}</div><div id="bench-results">${benchResults()}</div></section></div></div>`;}
function runControls(scope,run){return `${btn(scope==='bench'?'run-bench':'run-project',run.status==='paused'?'继续':'运行','Play',`data-command="run" ${['running','solving'].includes(run.status)?'disabled':''}`,'run small')}${btn(scope==='bench'?'run-bench':'run-project','暂停','Pause',`data-command="pause" ${run.status==='running'?'':'disabled'}`,'small')}${btn(scope==='bench'?'run-bench':'run-project','单步','StepForward',`data-command="step" ${['running','solving'].includes(run.status)?'disabled':''}`,'small')}${btn(scope==='bench'?'run-bench':'run-project','停止','Square',`data-command="stop" ${['ready','stopped'].includes(run.status)?'disabled':''}`,'small')}`;}
function renderHostBench(b,m) {
  const run=b.run,host=m.testConditions?.host_project,locked=['running','solving'].includes(run.status)?'disabled':'';
  return `<div class="page-shell">${heading('独立验证台','在封装时保留的完整宿主网络中验证开放设备组。',btn('edit-module','编辑模块','Pencil',`data-id="${m.id}"`)+btn('save','保存测试配置','Save'))}<div class="bench-layout"><aside class="stack"><section class="panel"><div class="panel-head"><h3>被测设备组</h3>${badge('开放制冷组 · v'+m.version,'blue')}</div><div class="panel-body stack"><label class="field"><span>模块</span><select data-bench-module aria-label="选择被测模块" ${locked}>${state.modules.filter(x=>x.runtime==='python').map(x=>option(x.id,x.name,m.id)).join('')}</select></label>${benchParamFields(m,b)}<small class="muted">参数仅用于此测试副本。</small></div></section><section class="panel"><div class="panel-head"><h3>宿主工况</h3></div><div class="panel-body stack">${host?`<strong data-host-project>${esc(host.name)}</strong><p>${host.instances.length} 台设备 · ${host.connections.length} 条连接 · ${esc(host.fluid.fluid)}</p><p class="muted">容器初始状态、制冷剂与外部连接使用封装时的系统快照。当前组参数代入该网络后进行真实求解。</p><dl><dt>被测实例</dt><dd>${esc(m.testConditions.host_instance_id || 'D1')}</dd><dt>公开端口</dt><dd>${m.ports.map(p=>esc(p.id)).join('、')}</dd></dl>`:'<p class="notice">缺少宿主工况，请在已连接的制冷项目中重新封装设备组。</p>'}<label class="field"><span>时间步长</span><div class="field-unit"><input type="number" data-bench-step ${locked} value="${run.step}" min=".01" max="10" step=".01"><span>s</span></div></label></div></section></aside><section class="panel"><div class="run-control"><div class="runtime"><strong>${esc(m.name)} · ${statusText(run)}</strong><span class="mono" data-bench-time>${clockLabel(run.time)}</span></div><span class="push"></span>${runControls('bench',run)}</div><div class="panel-body"><p class="notice">公开端口连接完整宿主回路；运行结果来自该回路中的被测设备组。</p></div><div class="tabs">${[['results','运行结果'],['events','事件记录']].map(([k,v])=>`<button data-action="bench-tab" data-value="${k}" class="${ui.benchTab===k?'active':''}">${v}</button>`).join('')}</div><div id="bench-results">${benchResults()}</div></section></div></div>`;
}
function benchResults() {
  if(state.bench.run.status==='failed')return `<div class="panel-body stack"><h3>模块测试失败</h3>${(state.bench.run.diagnostics||[]).map(d=>`<p>${esc(d.source_file||'')}${d.source_line?':'+d.source_line:''} · ${esc(d.message)}</p>`).join('')}${state.bench.run.failureReplay?btn('bench-failure-replay','带入验证台复现','Bug','','small'):'<p>此次错误未捕获完整回调输入。</p>'}</div>`;
  const b=state.bench,run=b.run,v=run.values,worker=run.worker,m=mod(b.moduleId);
  const benchChannels=(m.manifest?.channels || []).filter(c => c.enabled !== false);
  if (ui.benchTab === 'events') return `<div class="panel-body"><div class="notice">${icon('Info')}显示 Worker 生命周期与后端诊断。</div><div class="log-list">${run.events.slice().reverse().map(e=>`<div class="log-line"><time>${number(e.t,2)} s</time><span>${esc(e.text)}</span></div>`).join('') || empty('还没有测试事件','选择 Python 模块包后运行。')}</div></div>`;
  const table=(title,items)=>`<div class="panel-head"><h3>${title}</h3></div><div class="table-wrap"><table><thead><tr><th>字段</th><th>值</th></tr></thead><tbody>${Object.entries(items || {}).map(([key,value])=>`<tr><td class="mono">${esc(key)}</td><td class="mono">${esc(typeof value === 'object' ? JSON.stringify(value) : value)}</td></tr>`).join('') || '<tr><td colspan="2">尚无返回值</td></tr>'}</tbody></table></div>`;
  if(m.manifest?.sdk?.capabilities?.includes('composite.refrigeration.open.v1'))return `<div class="panel-body">${badge(worker?'宿主网络试算完成':'等待宿主网络试算',worker?'good':'')}<p class="muted">${worker?'返回公开端口状态、组内输出与状态别名；数值采用引擎单位。':'运行后显示真实回路中的设备组结果。'}</p></div>${table('设备组公开变量',worker?.evaluation.variables)}<div class="panel-body">${btn('record-bench','保存测试记录','Save','','small')}</div>`;
  return `<div class="metric-row"><div class="metric"><span>${benchChannels.length > 1 ? '通路合计流量' : '质量流量'}</span><strong data-bench-q>${number(run.history.length ? v.q : null,4)}</strong><small>kg/s · ${m.manifest?.schema_version===5 ? '制冷本构' : m.manifest?.execution_role ? '等焓节流' : (benchChannels.length || 1)+' 条通路'}</small></div><div class="metric"><span>边界压差</span><strong>${number(b.boundary.inlet-b.boundary.outlet,2)}</strong><small>kPa</small></div><div class="metric"><span>提交次数</span><strong data-bench-commits>${worker ? number(worker.committed.state.accepted_segments ?? worker.committed.state.commit_count,0) : '—'}</strong><small>commit_step</small></div></div>
  <div class="chart-panel"><div class="chart-heading"><h3>${m.manifest?.schema_version===5 ? '制冷本构流量' : m.manifest?.execution_role ? '节流质量流量' : '独立网络流量'}</h3><span class="push"></span>${badge(worker ? 'Worker 已完成 · v'+worker.version : '等待测试',worker ? 'good' : '')}</div>${chartSvg(run.history,['q'],'bench-chart')}<div class="chart-readout" id="bench-chart-readout">${clockLabel(run.time)} · ${esc(mod(b.moduleId).name)}</div></div>
  ${ui.benchTab === 'results' ? table('evaluate 变量与物性',worker?.evaluation.variables) + table('commit_step 状态',worker?.committed.state) + (m.manifest?.schema_version===5 ? table('本构守恒结果',worker?.constitutive?.result) : m.manifest?.execution_role ? table('制冷流股',worker?.refrigeration?.flow) : table('网络关系',Object.fromEntries((worker?.evaluation.relations || []).map(r=>[r.channel,{kind:r.kind,...r.parameters}])))) : ''}
  <div class="panel-body stack"><small class="muted mono" style="overflow-wrap:anywhere">${worker ? '内容哈希：'+esc(worker.contentHash) : '运行后返回实际求解流量、模块变量和状态。'}</small><div>${btn('record-bench','保存测试记录','Save','','small')}</div></div>`;
}
function currentChartRun(){if(state.charts.source!=='live')return state.records.find(r=>r.id===state.charts.source)||project().run;const run=project().run,overview=state.charts.range==='all'&&run.source==='engine'?engine.overview(run.id):null;return overview?.rows?{...run,history:overview.rows}:run;}
function overviewSeries(run) {
  const bindings=run.overviewBindings || (run.archive?engine.overviewBindings(run.archive.request.project):engine.overviewBindings(project()));
  for(const key of ['q','a','b','pressure','temperature']) {
    const binding=bindings[key];
    SERIES[key]={...SERIES[key],name:binding?.label || '未绑定',short:binding?.short || '未绑定'};
  }
  return bindings;
}
function renderCurves(...args){return runResultsView().renderCurves(...args);}
function renderRuns(...args){return runResultsView().renderRuns(...args);}

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
        params[uiName]=projectModel.toDisplay(spec,value);
      }
      return makeInstance(n.id,n.module_id,n.name,100+i*180,230,params);
    });
    const pg={id:'main',name:'控制回路',zoom:1,pan:[0,0],nodes,edges:model.connections.map(c=>[c.id,c.source.instance_id,c.source.port_id,c.target.instance_id,c.target.port_id])};
    const owner=makeProject(uid('project'),model.name,'内置 PID 验收示例',pg);
    owner.controllers=model.controllers;owner.solver.duration=button.dataset.kind==='level'?600:1200;owner.solver.dt=1;
    projectState.addProject(state,owner);normalizeState();markDirty(owner);openProject(owner.id);
  }catch(error){msg(error.message,true);}
});
const meterKinds = {value:'单点测量',difference:'两点差值',volume_flow:'体积流量',thermal_power:'热功率'};
function meterSources(p) {
  const result=[];
  const fields=[['pressure_pa','压力','pressure','Pa','kPa',1000,0],['temperature_k','温度','temperature','K','°C',1,-273.15],
    ['mass_flow_kg_s','质量流量','mass_flow','kg/s','kg/s',1,0],['density_kg_m3','密度','density','kg/m3','kg/m³',1,0],
    ['enthalpy_j_kg','比焓','specific_enthalpy','J/kg','kJ/kg',1000,0]];
  for(const n of p.pages.flatMap(pg=>pg.nodes)) {
    const m=moduleOf(n),d=m.manifest||engine.catalog?.modules.find(d=>d.id===m.kind);
    if(!d)continue;
    for(const v of d.variables.filter(v=>v.sampleable&&v.source!=='parameter'&&v.unit&&v.value_type==='number'))
      result.push({key:n.id+'.'+v.id,label:n.name+' · '+v.label,unit:clone(v.unit)});
    for(const port of d.ports)for(const [id,label,quantity,canonical_unit,display_unit,display_scale,display_offset] of fields)
      result.push({key:n.id+'.'+port.id+'.'+id,label:n.name+' · '+port.label+' · '+label,unit:{quantity,canonical_unit,display_unit,display_scale,display_offset}});
    for(const ch of d.channels.filter(c=>c.enabled))for(const [id,label,quantity,canonical_unit,display_unit,display_scale,display_offset] of fields.filter(f=>f[0]==='mass_flow_kg_s'))
      result.push({key:n.id+'.'+ch.id+'.'+id,label:n.name+' · '+ch.name+' · '+label,unit:{quantity,canonical_unit,display_unit,display_scale,display_offset}});
  }
  return result.filter((v,i)=>result.findIndex(s=>s.key===v.key)===i);
}
function meterValue(p,m) {
  const value=panelRow(p.run)?.canonical?.['measurement.'+m.id];
  return Number.isFinite(value)?number(value/m.unit.display_scale+m.unit.display_offset,3)+' '+esc(m.unit.display_unit):'—';
}
function meterPanel(p) {
  const disabled=p.run.live?'disabled':'';
  return `<section class="panel" style="margin-bottom:20px"><div class="panel-head"><h2>仪表与测点</h2><span class="push"></span>${Object.entries(meterKinds).map(([kind,label])=>btn('add-meter',label,'Plus',`data-kind="${kind}" ${disabled||((p.measurements||[]).length>=64?'disabled':'')}`,'small')).join('')}</div><div class="panel-body stack"><p class="muted">测点读取同一运行帧，可用于 PID 反馈和趋势。计算测点按所选输入的顺序求差；流量与热功率保留通路方向。</p>${(p.measurements||[]).map(m=>`<div class="row gap-6" data-meter-card="${esc(m.id)}"><strong>${esc(m.label)}</strong><span>${esc(meterKinds[m.kind])}</span><span class="push" data-meter-value="${esc(m.id)}">${meterValue(p,m)}</span>${btn('edit-meter','编辑','Pencil',`data-id="${esc(m.id)}" ${disabled}`,'small')}${btn('meter-curve','加入曲线','Activity',`data-id="${esc(m.id)}"`,'small')}${btn('remove-meter','移除','Trash2',`data-id="${esc(m.id)}" ${disabled}`,'small')}</div>`).join('')||'<p>尚未添加测点。</p>'}</div></section>`;
}
function editMeter(p,existing,kind) {
  const sources=meterSources(p),count={value:1,difference:2,volume_flow:2,thermal_power:3}[kind];
  const quantities=kind==='volume_flow'?['mass_flow','density']:kind==='thermal_power'?['mass_flow','specific_enthalpy','specific_enthalpy']:[];
  const choices=Array.from({length:count},(_,i)=>sources.filter(v=>!quantities[i]||v.unit.quantity===quantities[i]));
  if(choices.some(c=>!c.length))throw Error('当前设备没有这类测点所需的变量。');
  const labels=kind==='thermal_power'?['通路质量流量','出口比焓','入口比焓']:kind==='volume_flow'?['通路质量流量','通路密度']:kind==='difference'?['第一点','第二点']:['绑定变量'];
  openDialog(existing?'编辑测点':'添加'+meterKinds[kind],'数值按设备单位计算；测点可在控制反馈和曲线中选用。',
    field('label','测点名称',existing?.label||meterKinds[kind],'required maxlength="80"')+choices.map((items,i)=>selectField('source'+i,labels[i],items.map(s=>[s.key,s.label+' ('+s.unit.display_unit+')']),existing?.sources[i]||items[0].key)).join(''),data=>{
      if(project()!==p||p.run.live)throw Error('项目状态已改变，请重新编辑测点。');
      const selected=choices.map((items,i)=>items.find(v=>v.key===data['source'+i]));
      if(selected.some(v=>!v))throw Error('请选择有效的绑定变量。');
      if(kind==='difference'&&selected[0].unit.canonical_unit!==selected[1].unit.canonical_unit)throw Error('两点差值须选择相同单位的变量。');
      let unit=clone(selected[0].unit);
      if(kind==='difference'){unit.display_offset=0;if(unit.canonical_unit==='K')unit.display_unit='K';}
      if(kind==='volume_flow')unit={quantity:'volume_flow',canonical_unit:'m3/s',display_unit:'m³/h',display_scale:1/3600,display_offset:0};
      if(kind==='thermal_power')unit={quantity:'power',canonical_unit:'W',display_unit:'kW',display_scale:1000,display_offset:0};
      p.measurements||=[];
      const value={id:existing?.id||uid('meter'),label:data.label.trim(),kind,sources:selected.map(s=>s.key),unit};
      if(!value.label)throw Error('请填写测点名称。');
      if(existing)Object.assign(existing,value);else p.measurements.push(value);
      for(const chart of state.charts.extra.filter(c=>c.projectId===p.id&&c.canonicalKey==='measurement.'+value.id))Object.assign(chart,{label:value.label,unit:unit.display_unit,canonicalScale:unit.display_scale,canonicalOffset:unit.display_offset});
      markDirty(p);render();
    },'保存测点');
}
function measurementAction(action,button){
  const p=project(),m=p.measurements?.find(m=>m.id===button.dataset.id);
  try {
    if(button.dataset.action==='meter-curve'){if(m)addChartVariable('measurement.'+m.id,m.label);return;}
    if(p.run.live)return;
    if(button.dataset.action==='remove-meter') {
      if(p.controllers?.some(c=>c.measurement==='measurement.'+m.id)||controls.normalize(p).some(s=>(s.inputs||[]).includes('measurement.'+m.id)))throw Error('测点已被控制器或脚本使用，请先修改反馈绑定。');
      p.measurements=p.measurements.filter(v=>v!==m);
      p.selectedVariables=(p.selectedVariables||[]).filter(k=>k!=='measurement.'+m.id);
      state.charts.extra=state.charts.extra.filter(c=>c.projectId!==p.id||c.canonicalKey!=='measurement.'+m.id);
      markDirty(p);render();
    } else editMeter(p,m,m?.kind||button.dataset.kind);
  }catch(error){msg(error.message,true);}
}
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
  for(const m of p.measurements||[])measurements.push(['measurement.'+m.id,m.label+' ('+m.unit.canonical_unit+')']);
  return {measurements,targets};
}
function projectSettingsLocked(p=project()) {
  return !!p.run.live || ['running','solving','paused'].includes(p.run.status);
}
function assertProjectSettingsEditable(p=project()) {
  if(projectSettingsLocked(p))throw Error('请先停止运行，再修改介质与求解设置。');
}
function restoreProjectSettingInput(el) {
  const d=el.dataset,p=project();let value;
  if('solverContinuous' in d){el.checked=!!p.solver.continuous;return;}
  if(d.solverField)value=p.solver[d.solverField];
  else if(d.solverOption)value=p.solverOptions?.[d.solverOption] ?? 'reference';
  else if('liveMode' in d)value=p.solver.executionMode ?? 'realtime';
  else if('liveSpeed' in d)value=p.solver.speedRatio ?? 1;
  else if('projectPhasePolicy' in d)value=p.fluidConfig?.phase_policy ?? 'single_phase';
  else if(d.projectField)value=p[d.projectField] ?? (d.projectField==='fluidReference'?'mass':'');
  else if(d.circuitField){
    const row=p.circuitFluids?.[Number(d.index)];if(!row)return;
    value=d.circuitField==='anchor'?`${row.anchor?.instance_id||''}:${row.anchor?.port_id||''}`
      :row[d.circuitField] ?? ({medium:'water',fluidReference:'mass'}[d.circuitField]||'');
  }else return;
  el.value=value ?? '';
}
function executionSettings(p) {
  const locked=projectSettingsLocked(p)||p.solver.mode==='steady',pace=p.solver.executionMode||'realtime';
  return `<label class="field"><span>计算节奏</span><select data-live-mode ${locked?'disabled':''}>${option('realtime','按真实时间运行',pace)}${option('fast','快速计算',pace)}</select></label><label class="field"><span>速度倍率</span><input data-live-speed type="number" min="0.1" max="100" step="any" value="${p.solver.speedRatio ?? 1}" ${locked||pace==='fast'?'disabled':''}><small class="muted">仅按真实时间运行时使用。</small></label>`;
}
function pidPanel(p) {
  const {measurements,targets}=pidOptions(p), active=!!p.run.live;
  const fields=[['setpoint','设定值'],['kp','比例 Kp'],['ki','积分 Ki（每秒）'],['kd','微分 Kd（秒）'],['sample_s','采样周期（秒）'],['minimum','输出下限'],['maximum','输出上限'],['manual_output','手动输出']];
  return `<section class="panel" style="margin-bottom:20px"><div class="panel-head"><h2>PID 反馈控制</h2>${btn('pid-example','液位示例','Droplets','data-kind="level"','small')}${btn('pid-example','温控示例','Thermometer','data-kind="temperature"','small')}${btn('add-pid','添加控制器','Plus',active?'disabled':'','small')}</div><div class="panel-body stack"><p class="muted">选择反馈变量和执行参数。数值使用选项标注的单位；运行中可调整设定值及手自动模式。</p><div class="fields">${executionSettings(p)}</div>${(p.controllers || []).map(c=>`<section class="panel" data-pid-card="${esc(c.id)}"><div class="panel-head"><strong>${esc(c.id)}</strong>${btn('remove-pid','移除','Trash2',`data-id="${esc(c.id)}" ${active?'disabled':''}`,'small')}</div><div class="panel-body fields"><label class="field"><span>反馈变量</span><select data-pid-id="${esc(c.id)}" data-pid-field="measurement" ${active?'disabled':''}>${measurements.map(([v,l])=>option(v,l,c.measurement)).join('')}</select></label><label class="field"><span>执行参数</span><select data-pid-id="${esc(c.id)}" data-pid-field="target" ${active?'disabled':''}>${targets.map(([v,l])=>option(v,l,c.instance_id+'.'+c.parameter_id)).join('')}</select></label><label class="field"><span>模式</span><select data-pid-id="${esc(c.id)}" data-pid-field="mode">${option('auto','自动',c.mode)}${option('manual','手动',c.mode)}</select></label>${fields.map(([key,label])=>`<label class="field"><span>${label}</span><input type="number" step="any" data-pid-id="${esc(c.id)}" data-pid-field="${key}" value="${c[key] ?? ''}" ${active && !['setpoint','manual_output'].includes(key)?'disabled':''}></label>`).join('')}</div><div class="panel-body" data-pid-readout="${esc(c.id)}">${pidReadout(p,c)}</div></section>`).join('') || '<p>尚未配置控制器；可先运行模型，再选择反馈变量。</p>'}</div></section>`;
}
function pidReadout(p,c) {
  const row=panelRow(p.run)?.canonical || {};
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
  if(!el.dataset.pidField) return;
  const c=p.controllers.find(c=>c.id===el.dataset.pidId),key=el.dataset.pidField;
  if(!c) return;
  try {
    const value=['mode','measurement','target'].includes(key)?el.value:Number(el.value);
    if(p.run.live) await engine.applyController(p,c.id,key,value);
    if(key==='target') {
      [c.instance_id,c.parameter_id]=value.split('.');
      const spec=pidOptions(p).targets.find(t=>t[0]===value)[2];
      c.minimum=spec.minimum ?? -10000;c.maximum=spec.maximum ?? 10000;c.manual_output=spec.default;
    } else c[key]=value;
    markDirty(p);render();
  } catch(error) {msg(error.message,true);render();}
});
function controlLiveValues(p=project()){
  const values=panelRow(p.run)?.canonical||{}, keys=new Set((p.controlOutputs||'').split(/[\s,，]+/));
  return JSON.stringify(Object.fromEntries(Object.entries(values).filter(([key])=>keys.has(key)||key.startsWith(`script.${p.selectedControlId}.`))),null,2);
}
function renderControls(){const p=project(),programs=controls.normalize(p),selected=controls.current(p);return `<div class="page-shell">${heading('项目控制逻辑','按脚本组织控制策略；修改会在下次新运行生效。',btn('control-template','载入示例','FileCode2',selected?'':'disabled')+btn('control-template','载入机房联锁','ShieldCheck',(selected?'':'disabled')+' data-kind="interlock"','small')+btn('preview-control','预览一个周期','StepForward',selected?'':'disabled','primary')+btn('save','保存脚本','Save'))}${meterPanel(p)}${pidPanel(p)}<section class="panel" style="margin-bottom:20px"><div class="panel-head"><h2>控制脚本</h2>${badge(programs.length+' / '+controls.MAX_PROGRAMS)}<span class="push"></span>${btn('add-control-program','新建脚本','Plus',programs.length>=controls.MAX_PROGRAMS?'disabled':'','small')}${btn('remove-control-program','删除所选脚本','Trash2',selected?`data-id="${esc(selected.id)}"`:'disabled','small')}</div><div class="panel-body">${programs.length?`<label class="field"><span>当前脚本</span><select data-control-program aria-label="选择控制脚本">${programs.map(program=>option(program.id,`${program.name} · ${program.id} · ${program.language!=='python'?'待迁移':program.enabled?'已启用':'未启用'}`,p.selectedControlId)).join('')}</select></label>`:'<p>尚无控制脚本。新建脚本后可编辑、预览并单独启用。</p>'}</div></section>${selected?`<details open><summary>编辑 ${esc(selected.id)}</summary><div class="connection-layout"><aside class="stack"><section class="panel"><div class="panel-head"><h3>控制程序</h3>${badge(p.controlLanguage==='python'?'Python':'旧脚本待迁移',p.controlLanguage==='python'?'good':'warn')}</div><div class="panel-body stack">
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
  if(ui.connectionTab==='api')return `<div class="connection-layout"><aside class="stack"><h3>调用场景</h3><div class="side-nav">${[['read','读取变量','ArrowDownToLine'],['set','批量写入','Pencil'],['stream','订阅推送','Activity'],['status','运行状态','Info']].map(([k,l,i])=>`<button class="${(ui.apiKind||'read')===k?'active':''}" data-action="api-example" data-value="${k}">${icon(i)}${l}</button>`).join('')}</div><label class="field"><span>当前运行</span><input value="${esc(apiRunId()||'尚未运行')}" readonly></label><div class="notice">${icon('Info')}<span>${engine.health?.auth?.required?'服务已开启令牌认证：外部调用需要 Authorization 头。':'服务只监听本机，未开启认证；对外开放前请用令牌启动（见 README）。'}</span></div></aside><div class="stack"><div class="row">${btn('api-refresh','刷新变量目录','RefreshCw','','small ghost')}</div><div id="api-target"></div><div class="row"><span class="badge blue">GET</span><strong class="mono" id="api-path"></strong><span class="push"></span>${btn('api-preview','发送请求','Play','','primary')}</div><div class="code-preview" id="api-request"></div><div class="code-output" id="api-response" role="status"></div></div></div>`;
  if(ui.connectionTab==='serial'){const c=state.connectors.find(c=>c.id===ui.selectedConnector&&c.kind==='serial')||state.connectors.find(c=>c.kind==='serial');return `<div class="connection-layout"><aside class="stack"><div class="row spread"><h3>串口连接</h3>${ibtn('add-connector','添加串口连接','Plus')}</div><div class="side-nav">${state.connectors.filter(c=>c.kind==='serial').map(c=>`<button data-action="select-connector" data-id="${c.id}" class="${c.id===ui.selectedConnector?'active':''}">${icon('Plug')}<span>${esc(c.name)}<small class="muted" style="display:block">${c.port} · ${c.baud}</small></span></button>`).join('')}</div><div class="notice">${icon('Info')}串口打开和收发仅模拟状态，不访问硬件。</div></aside><div class="stack"><div class="row spread"><div><h3>${esc(c.name)}</h3><small class="muted">保存后保留连接参数</small></div>${badge(c.connected?'演示已连接':'未连接',c.connected?'good':'')}</div><div class="fields"><label class="field"><span>端口</span><select data-connector-id="${c.id}" data-connector-field="port">${['COM1','COM3','COM5'].map(x=>option(x,x,c.port)).join('')}</select></label><label class="field"><span>波特率</span><select data-connector-id="${c.id}" data-connector-field="baud">${['9600','19200','57600','115200'].map(x=>option(x,x,c.baud)).join('')}</select></label><label class="field"><span>数据位</span><select data-connector-id="${c.id}" data-connector-field="bits">${option('8','8',c.bits||'8')}${option('7','7',c.bits||'8')}</select></label><label class="field"><span>校验位</span><select data-connector-id="${c.id}" data-connector-field="parity">${['None','Even','Odd'].map(x=>option(x,x,c.parity||'None')).join('')}</select></label></div><div class="row">${btn('connect-demo',c.connected?'断开演示':'连接演示','Plug',`data-id="${c.id}"`,'primary')}<small class="muted">${c.connected?'可以模拟一条消息收发':'尚未启动模拟连接'}</small></div><div class="spacer"></div><h3>发送消息</h3><div class="row"><input id="serial-message" aria-label="串口模拟发送消息" value="#Get/V1.OPENING" style="flex:1">${btn('serial-send','模拟发送','ArrowUpRight',`data-id="${c.id}" ${c.connected?'':'disabled'}`)}</div><div class="code-output" id="serial-output" role="status">等待模拟消息。</div></div></div>`;}
  if(ui.connectionTab==='bindings')return `<div class="stack"><div class="row spread"><div><h3>输入输出映射</h3><p class="muted" style="font-size:12px;margin-top:4px">给外部字段指定变量、方向与单位。</p></div>${btn('add-binding','添加映射','Plus','','primary')}</div><div class="table-wrap"><table><thead><tr><th>外部字段</th><th>项目变量</th><th>方向</th><th>单位</th><th>状态</th></tr></thead><tbody id="binding-rows">${bindingsForProject().map((b,i)=>`<tr><td class="mono">${esc(b.external)}</td><td><select data-binding-index="${i}" aria-label="映射 ${i+1} 的变量">${projectVariables().filter(v=>b.direction!=='write'||v.writable).map(v=>option(v.id,v.id+' · '+v.name,b.variable)).join('')}</select></td><td>${badge(b.direction==='write'?'外部 → 项目':'项目 → 外部',b.direction==='write'?'warn':'blue')}</td><td>${esc(b.unit)}</td><td>${badge('未连接')}</td></tr>`).join('')}</tbody></table></div><div class="notice">${icon('Info')}外部写入目标的类型、范围和单位需与变量定义一致；此处仅保存映射配置。</div></div>`;
  return `<div class="stack"><div class="row spread"><h3>消息与事件</h3><div class="row">${badge(state.messages.length+' 条记录')}${btn('demo-message','生成示例消息','Plus','','small')}${btn('export','导出消息','Download','data-format="messages"','small')}</div></div><div class="log-list" style="max-height:560px">${state.messages.map(m=>`<div class="log-line"><time>${esc(m.time)}</time><span class="log-kind">${esc(m.kind)}</span><span>${esc(m.text)}</span></div>`).join('')}</div></div>`;
}
function anchorOptions(p){return p.pages.flatMap(pg=>pg.nodes).flatMap(n=>moduleOf(n).ports.filter(port=>['fluid','refrigerant'].includes(port.domain)).map(port=>[`${n.id}:${port.id}`,`${n.id} ${n.name} · ${port.label||port.id}`]));}
function circuitAnchorOptions(anchors,row){
  const selected=`${row.anchor?.instance_id||''}:${row.anchor?.port_id||''}`;
  const missing=anchors.some(([value])=>value===selected)?'':`<option value="${esc(selected)}" selected disabled>${esc(selected)} · 端口已失效，请重新选择</option>`;
  return missing+anchors.map(([value,label])=>option(value,label,selected)).join('');
}
function circuitFluidsMarkup(p){
  const rows=p.circuitFluids||[],anchors=anchorOptions(p),circuits=engine.circuits?.(p.id)||[];
  return `<div class="settings-section"><div class="row spread"><h3>回路工质</h3>${btn('add-circuit-fluid','添加回路工质','Plus',anchors.length?'':'disabled','small')}</div><p class="muted">端口经连接和设备内部通路连成一个回路（关闭的阀门不分隔回路，换热器两侧是两个回路）。选一个端口代表回路并指定工质，其余回路用上面的默认介质。</p>${rows.map((c,i)=>`<div class="fields" data-circuit-row="${i}"><label class="field"><span>回路端口</span><select data-circuit-field="anchor" data-index="${i}">${circuitAnchorOptions(anchors,c)}</select></label><label class="field"><span>预设介质</span><select data-circuit-field="medium" data-index="${i}">${MEDIA.map(([k,n])=>option(k,n,c.medium||'water')).join('')}</select></label><label class="field"><span>物性字符串（可选）</span><input data-circuit-field="fluid" data-index="${i}" value="${esc(c.fluid||'')}" placeholder="如 REFPROP::R134A" spellcheck="false"></label><label class="field"><span>比例基准</span><select data-circuit-field="fluidReference" data-index="${i}">${option('mass','质量分数',c.fluidReference||'mass')}${option('mole','摩尔分数',c.fluidReference||'mass')}</select></label>${btn('remove-circuit-fluid','移除','Trash2',`data-index="${i}"`,'small')}</div>`).join('')||'<p>所有回路使用默认介质。</p>'}${circuits.length>1?`<div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>回路</th><th>工质</th><th>来源</th><th>端口数</th></tr></thead><tbody>${circuits.map(c=>`<tr><td><span class="series-key" style="background:${CIRCUIT_COLORS[c.id%CIRCUIT_COLORS.length]}"></span> ${c.id+1}</td><td>${esc(c.fluid.fluid)}</td><td>${esc(c.source==='project'?'项目默认':c.source)}</td><td>${c.ports.length}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted" style="font-size:12px">点击画布上的“检查连接”后显示各回路及其工质。</p>'}</div>`;
}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action="add-circuit-fluid"],[data-action="remove-circuit-fluid"]');
  if(!button) return;
  try {
    const p=project();assertProjectSettingsEditable(p);
    if(button.dataset.action==='remove-circuit-fluid') p.circuitFluids?.splice(Number(button.dataset.index),1);
    else {
      const anchors=anchorOptions(p);if(!anchors.length)throw Error('请先添加具有流体或制冷剂端口的设备。');
      const [instance_id,port_id]=anchors[0][0].split(':');
      (p.circuitFluids ||= []).push({id:'circuit_'+Date.now(),anchor:{instance_id,port_id},medium:'meg30',fluid:'',fluidReference:'mass'});
    }
    markDirty(p);render();
  }catch(error){msg(error.message,true);}
});
function renderSettings(){
  const configuration=['medium','solver'].includes(ui.settingsTab),locked=configuration&&projectSettingsLocked();
  const content=settingsContent();
  return `<div class="page-shell">${heading('项目与工作台设置','配置项目、介质、求解参数与界面偏好。',btn('save','保存设置','Save','','primary'))}<div class="settings-layout"><aside class="side-nav">${[['project','项目属性','Folder'],['medium','介质与单位','Droplets'],['solver','运行与求解','SlidersHorizontal'],['appearance','界面与布局','Monitor'],['storage','保存与交换','Database']].map(([k,l,i])=>`<button data-action="settings-tab" data-value="${k}" class="${ui.settingsTab===k?'active':''}">${icon(i)}${l}</button>`).join('')}</aside><section class="panel">${locked?`<div class="settings-section"><div class="notice" role="status">请先停止当前运行，再修改介质与求解设置。${btn('nav','返回画布','ArrowRight','data-route="workbench"','ghost small')}</div></div>`:''}${configuration?`<fieldset style="border:0;margin:0;padding:0;min-width:0" aria-label="项目运行配置" ${locked?'disabled':''}>${content}</fieldset>`:content}</section></div></div>`;
}
function solverSettingsMarkup(p){
  const steady=p.solver.mode==='steady',moist=!!p.solverOptions?.moist_air,coupling=p.solverOptions?.property_coupling||'reference';
  return `<div class="settings-section"><h3>运行设置</h3><p>${steady?'稳态运行只求解一个工况；单步按动态设置推进。仿真时长、持续运行、输出间隔与计算节奏需切换到动态模式后调整。':'设置仿真时长、输出间隔及停止条件。'}</p><div class="fields">
    <label class="field"><span>运行模式</span><select data-solver-field="mode">${option('dynamic','动态',p.solver.mode)}${option('steady','稳态',p.solver.mode)}</select></label>${executionSettings(p)}
    <label class="field"><span>仿真时长</span><div class="field-unit"><input type="number" data-solver-field="duration" value="${p.solver.duration}" min="1" max="86400" step="any" ${steady||p.solver.continuous?'disabled':''}><span>s</span></div></label>
    <label class="check-label"><input type="checkbox" data-solver-continuous ${p.solver.continuous?'checked':''} ${steady?'disabled':''}>持续运行（仅动态；不设时长，直到停止；浏览器保留最近 2001 帧，曲线页可看全程抽稀）</label>
    <label class="field"><span>输出间隔</span><div class="field-unit"><input type="number" data-solver-field="dt" value="${p.solver.dt}" min=".01" max="60" step="any" ${steady?'disabled':''}><span>s</span></div></label>
    <label class="field"><span>最大迭代次数</span><input type="number" data-solver-field="maxIter" value="${p.solver.maxIter}" min="5" max="500" step="1"></label>
    <label class="field"><span>物性反馈</span><select data-solver-option="property_coupling"><option value="reference" ${coupling==='reference'?'selected':''} ${moist?'disabled':''}>参考物性（水力独立）</option>${option('node','温度与密度联算',coupling)}</select>${moist?'<small class="muted">湿空气计算必须使用温度与密度联算。</small>':''}</label>
    <label class="field"><span>水力算法</span><select data-solver-field="hydraulicMethod">${option('auto','自动（按未知量与稀疏度）',p.solver.hydraulicMethod||'auto')}${option('dense','稠密',p.solver.hydraulicMethod)}${option('sparse','稀疏',p.solver.hydraulicMethod)}</select></label>
    </div></div><div class="settings-section"><h3>收敛判据</h3><p>质量与压力使用独立容差；数值设置需要在真实求解阶段验证。</p><div class="fields">
    <label class="field"><span>质量绝对容差</span><div class="field-unit"><input type="number" data-solver-field="massAtol" step="any" value="${p.solver.massAtol}" min="1e-12" max="1"><span>kg/s</span></div></label>
    <label class="field"><span>压力绝对容差</span><div class="field-unit"><input type="number" data-solver-field="pressureAtol" step="any" value="${p.solver.pressureAtol}" min="1e-12" max="100000"><span>Pa</span></div></label>
    </div></div>`;
}
function settingsContent(){const p=project();
  if(ui.settingsTab==='project')return `<div class="settings-section"><h3>项目属性</h3><p>名称和说明用于项目列表、运行记录与导出文件。</p><div class="fields"><label class="field"><span>项目名称</span><input data-project-field="name" value="${esc(p.name)}" maxlength="50" aria-label="项目名称"></label><label class="field"><span>项目标识</span><input value="${p.id}" readonly></label><label class="field wide"><span>项目说明</span><textarea data-project-field="description" aria-label="项目说明" maxlength="240">${esc(p.description)}</textarea></label></div></div><div class="settings-section"><div class="row spread"><h3>画布</h3>${btn('new-canvas','添加画布','Plus','','small')}</div>${p.pages.map(pg=>`<div class="list-row" style="padding:12px 0">${icon('Layers')}<div class="grow"><strong>${esc(pg.name)}</strong><small>${pg.nodes.length} 个设备 · ${pg.edges.length} 条连接</small></div>${btn('rename-canvas','重命名','Pencil',`data-id="${pg.id}"`,'small ghost')}</div>`).join('')}</div>`;
  if(ui.settingsTab==='medium')return `<div class="settings-section"><h3>介质配置</h3><p>默认介质用于没有单独指定工质的回路；温度和压力范围由计算服务按各回路的流体检查。</p><div class="fields"><label class="field"><span>默认介质</span><select data-project-field="medium">${MEDIA.map(([key,name])=>option(key,name,p.medium)).join('')}</select></label><label class="field wide"><span>物性字符串（可选，填写后替代默认介质）</span><input data-project-field="fluid" value="${esc(p.fluid||'')}" placeholder="如 REFPROP::R407C.MIX、REFPROP::R32[0.5]&amp;R125[0.5]、HEOS::R134a" aria-label="物性字符串" spellcheck="false"></label><label class="field"><span>组分比例基准</span><select data-project-field="fluidReference">${option('mass','质量分数',p.fluidReference||'mass')}${option('mole','摩尔分数',p.fluidReference||'mass')}</select></label><label class="field"><span>相态策略</span><select data-project-phase-policy aria-label="项目相态策略">${[['single_phase','单相'],['liquid','液相'],['gas','气相'],['any','按设备模型检查（制冷容器含两相）']].map(([key,label])=>option(key,label,p.fluidConfig?.phase_policy||'single_phase')).join('')}</select></label><label class="field"><span>显示单位方案</span><input value="工程单位 · 本轮原型" readonly></label></div>${circuitFluidsMarkup(p)}<p class="muted" style="font-size:12px">${(()=>{const r=engine.health?.capabilities?.refprop;if(!r?.installed)return '未检测到 REFPROP；可将内置副本放到 vendor/refprop9.1/，或设置 FLUIDNET_REFPROP_PATH，或安装到 Windows 默认安装目录。';const src={bundled:'内置',env:'环境变量',system:'系统安装'}[r.source]||'未知来源';return `已检测到 REFPROP${r.version?' '+esc(r.version):''}（${esc(src)}），可使用 REFPROP:: 前缀（纯质写名称，混合物写 A[x]&amp;B[y] 或预定义的 名称.MIX）。`})()}</p><div class="notice" style="margin-top:20px">${icon('Droplets')}换热器两侧回路保留独立的介质归属，不通过图形分组自动合并。</div></div><div class="settings-section"><h3>物理量与单位</h3><div class="table-wrap"><table><thead><tr><th>物理量</th><th>工程显示</th><th>内部约定</th></tr></thead><tbody>${[['绝对压力','kPa / MPa','Pa'],['温度','°C','K'],['质量流量','kg/s','kg/s'],['比焓','kJ/kg','J/kg'],['密度','kg/m³','kg/m³'],['比容','m³/kg','m³/kg']].map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="muted" style="margin:12px 0 0;font-size:12px">密度与比容是不同物理量，独立命名与换算。</p></div>`;
  if(ui.settingsTab==='solver')return solverSettingsMarkup(p);
  if(ui.settingsTab==='appearance')return `<div class="settings-section"><h3>界面显示</h3><p>切换主题与画布辅助显示，浏览器会记住偏好。</p><div class="fields"><label class="field"><span>主题</span><select data-theme-select>${option('light','浅色',ui.theme)}${option('dark','深色',ui.theme)}</select></label><label class="field"><span>模块与设备变量显示精度</span><select data-module-precision aria-label="模块与设备变量显示精度">${option('','按模块定义',ui.modulePrecision??'')}${[2,4,6,8].map(n=>option(n,n+' 位小数',ui.modulePrecision)).join('')}</select><small>统一调整本浏览器中的模块、设备变量及型号变量预览的小数位数。</small></label></div><div style="margin-top:20px"><label class="check-label"><input type="checkbox" data-ui-toggle="pageGrid" ${ui.pageGrid?'checked':''}>显示画布点阵</label></div></div><div class="settings-section"><h3>窗口布局</h3><p>参数窗口可以移动、调整大小、置顶和收起。关闭查看窗口不会终止运行。</p>${btn('reset-windows','恢复窗口位置','Columns2')}${btn('nav','到画布查看','ArrowRight','data-route="workbench"','ghost')}</div><div class="settings-section"><h3>键盘操作</h3><div class="shortcut-grid" style="margin-top:15px">${shortcutMarkup()}</div></div>`;
  return `<div class="settings-section"><h3>原型保存</h3><p>保存当前浏览器中的项目、模块、型号、参数和配置。</p><div class="notice good">${icon('Database')}<span>${state.savedAt?'已保存原型草稿；再次保存会更新这份浏览器记录。':'当前使用内置示例，点击保存后记录你的编辑。'}</span></div><div class="row wrap" style="margin-top:18px">${btn('save','保存原型','Save','','primary')}${btn('export','导出原型 JSON','Download','data-format="prototype"')}${btn('import','导入原型 JSON','Upload')}</div></div><div class="settings-section"><h3>数据交换</h3><p>原型交换文件仅用于此设计版本，不直接修改正式项目工作区。</p><div class="row wrap">${btn('export','导出型号库','Database','data-format="models"')}${btn('export','导出变量表','Table2','data-format="variables"')}</div></div><div class="settings-section"><h3>恢复示例</h3><p>开始一轮新的原型体验前，可以先导出当前数据，再恢复示例。</p>${btn('reset-prototype','恢复内置示例','RotateCcw','','danger')}</div>`;
}
function shortcutMarkup(){return [['保存原型','Ctrl S'],['页面导航','Ctrl K'],['撤销 / 重做','Ctrl Z / Y'],['复制 / 粘贴设备','Ctrl C / V'],['删除选中对象','Delete'],['取消连线 / 关闭弹窗','Esc']].map(([label,key])=>`<div><span>${label}</span><kbd>${key}</kbd></div>`).join('');}
function renderHelp(){return `<div class="page-shell">${heading('页面导览与使用指南','先用已有设备完成一次调参，再按需进入自定义模块开发。',btn('page-map','页面导航','LayoutDashboard')+btn('start-modeling','从示例调参开始','ArrowRight','','primary')+btn('guided-demo','进入模块开发','Code2'))}<div class="journey">${[['01','打开示例','选择已有管网与设备'],['02','调整参数','编辑草稿，核对当前值'],['03','明确应用','确认变化与生效时刻'],['04','运行或单步','更新当前参数对应的结果'],['05','观察与保存','同屏对照曲线、保存记录']].map(([n,t,d])=>`<div class="journey-step"><span class="step-number">${n}</span><strong>${t}</strong><p>${d}</p></div>`).join('')}</div><div class="section-title"><h2>所有页面</h2><span class="muted">${Object.keys(PAGE_META).length} 个页面 · ${EDITOR_TABS.length} 个模块编辑页签</span></div><div class="help-grid">${Object.entries(PAGE_META).filter(([id])=>id!=='help').map(([id,[name,i,desc]])=>`<article class="help-card">${icon(i)}<h3>${name}</h3><p>${desc}</p>${btn('nav','打开页面','ArrowUpRight',`data-route="${id}"`,'small')}</article>`).join('')}</div><div class="fields" style="margin-top:22px"><section class="panel"><div class="panel-head"><h3>三个不同的对象</h3></div><div class="panel-body stack"><p><strong>模块定义</strong><br><span class="muted">描述图形、端口、变量、通路和算法。</span></p><p><strong>设备型号</strong><br><span class="muted">保存一组命名参数，并保留版本。</span></p><p><strong>项目实例</strong><br><span class="muted">放在项目中的设备，可单独改参数。</span></p></div></section><section class="panel"><div class="panel-head"><h3>保存、应用与运行</h3></div><div class="panel-body stack"><p><strong>保存</strong>：保留当前编辑草稿。</p><p><strong>应用</strong>：检查差异，将参数写入当前设备。</p><p><strong>运行</strong>：推进项目运行并记录结果。</p><div class="notice">${icon('Info')}项目通过后端求解；Python 模块包在独立 Worker 中执行。Python 控制脚本可预览，启用后在新建动态运行中执行。</div></div></section></div><section class="panel" style="margin-top:20px"><div class="panel-head"><h3>常用快捷键</h3></div><div class="panel-body shortcut-grid">${shortcutMarkup()}</div></section></div>`;}

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
      const def = moduleParamDefs(m).find(f => f[0] === v.param);
      if (def) numeric(value, def[3], def[4]);
    } catch (error) { throw Error(`${v.label}：${error.message}`); }
  }
}
function instanceBankDiff(n, bank) {
  const data = ensureInstanceVariables(n);
  return moduleOf(n).variables.filter(v => instanceWritable(v) && !sameValue(instanceVariableValue(n, v), data.banks[bank][v.id]));
}
let deviceApplicationController;
function deviceApplications(){return deviceApplicationController ||= FluidNetDeviceApplication.create({
  state:()=>state,projectRunState,projectState,engine,performance:FluidNetPerformanceData,
  clone,sameValue,ownerOfInstance,moduleOf,instanceWritable,ensureInstanceVariables,
  validateInstanceEdits,markDirty,remember,render
});}
function instanceApplication(n,values,bank=-1){return deviceApplications().capture(n,values,bank);}
function applyInstanceApplication(owner,n,application){return deviceApplications().apply(owner,n,application);}
function applyInstanceBank(n, bank) {
  const values = instanceEdits(n, bank), differences = instanceBankDiff(n, bank);
  validateInstanceEdits(n, values);
  const owner = ownerOfInstance(n),application=instanceApplication(n,values,bank);
  openDialog(`库值 ${bank + 1} → ${n.id} · ${n.name}`, `仅应用可编辑参数与自定义变量，端口结果和项目系统设置保持只读。${pendingCount(n) ? '确认后会替换这台设备已有的待应用草稿。' : ''}`,
    diffMarkup(differences.map(v => [`${v.label} · ${v.unit}`, instanceVariableValue(n, v), values[v.id]])), async () => {
      try {
        await applyInstanceApplication(owner,n,application);
        owner.run.events.push({ t: owner.run.time, kind: 'parameters', text: `${n.id} 应用库值 ${bank + 1}：${differences.map(v => `${v.name}=${values[v.id]}`).join('，')}` });
        msg(`${n.id} 的库值 ${bank + 1} 已应用`);
      } catch(error) {msg(error.message,true);}
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
  const digits = ui.modulePrecision ?? precision;
  return Array.isArray(value) ? value.map(n => number(n, v.type.startsWith('int') ? 0 : digits)).join(', ') : number(value, v.type === 'int' ? 0 : digits);
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
    ['runtime', '计算结果', m.variables.filter(v => v.origin === 'runtime')],
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
    <div class="instance-filters"><label class="search">${icon('Search')}<input data-instance-search="${n.id}" aria-label="${n.id} 搜索全部变量" value="${esc(config.search)}" placeholder="中文名称、变量标识"></label><select data-instance-group="${n.id}" aria-label="${n.id} 变量分组">${[['all', '全部分组'], ['parameter', '设备参数'], ['port', '端口变量'], ['runtime', '计算结果'], ['custom', '自定义变量'], ['system', '系统变量']].map(([key, label]) => option(key, label, config.group)).join('')}</select><label class="instance-edit-source">编辑<select data-instance-source-select="${n.id}" aria-label="${n.id} 编辑目标">${option(-1, '待应用草稿', config.source)}${data.bankNames.map((name, i) => option(i, '库值 ' + (i + 1) + ' · ' + name, config.source)).join('')}</select></label></div>
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
    projectState.setVariableDraft(ownerOfInstance(n),n,v,source,result);
    markDirty(ownerOfInstance(n)); renderFloats();
  }, '保存到草稿');
}
function updateInstanceVariableInput(el) {
  const n = instance(el.dataset.id), v = moduleOf(n).variables.find(v => v.id === el.dataset.instanceValue);
  if (!v || !instanceWritable(v) || v.type.endsWith('[8]')) return;
  const source = Number(el.dataset.instanceSource), data = ensureInstanceVariables(n), value = el.value === '' ? '' : Number(el.value);
  projectState.setVariableDraft(ownerOfInstance(n),n,v,source,value);
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
    const boxes=pg.nodes.map(n=>{const m=moduleOf(n),b=FluidNetCanvasSymbols.hitBounds(n,m),r=(n.rotation||0)*Math.PI/180;
      const points=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y])=>({x:n.x+x*Math.cos(r)-y*Math.sin(r),y:n.y+x*Math.sin(r)+y*Math.cos(r)}));
      return {left:Math.min(...points.map(p=>p.x)),right:Math.max(...points.map(p=>p.x)),top:Math.min(...points.map(p=>p.y))-16,bottom:Math.max(...points.map(p=>p.y),n.y+FluidNetCanvasSymbols.labelY(n,m)+48)};});
    const left=Math.min(...boxes.map(b=>b.left))-30,top=Math.min(...boxes.map(b=>b.top))-30;
    pg.viewBounds=[left,top,Math.max(240,Math.max(...boxes.map(b=>b.right))-left+30),Math.max(240,Math.max(...boxes.map(b=>b.bottom))-top+30)];
  }
  pg.zoom = 1; pg.pan = [0, 0];
}

function networkViewBox(pg) {
  const valid = Array.isArray(pg.viewBounds) && pg.viewBounds.length === 4 && pg.viewBounds.every(Number.isFinite) && pg.viewBounds[2] > 0 && pg.viewBounds[3] > 0;
  const [x, y, width, height] = valid ? pg.viewBounds : [-35, -5, 1140, 510], zoom = pg.zoom || 1;
  return `${x + (width - width / zoom) / 2 - pg.pan[0]} ${y + (height - height / zoom) / 2 - pg.pan[1]} ${width / zoom} ${height / zoom}`;
}

function projectParameterKey(owner=project()){return projectModel.parameterKey(owner,state.modules,controls.key);}

function workbenchResultState() {
  const run = project().run;
  if (!panelRow(run)) return { text: '尚未采样 · 运行或单步查看结果', tone: '' };
  if (!run.parameterKey) return { text: '已有结果 · 请单步核对当前参数', tone: 'warn' };
  if (run.parameterKey !== projectParameterKey()) return { text: '参数已变更 · 等待重新采样', tone: 'warn' };
  if (replayingKeyFrame(run)) return { text: `结果已更新 · ${clockLabel(run.history.at(-1).t)} · 回放：显示最近关键帧`, tone: 'good' };
  return { text: `结果已更新 · ${clockLabel(panelRow(run).t)}`, tone: 'good' };
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
    projectState.addProject(state,p); normalizeState(); markDirty(p);
  }
  ui.showChart = true; ui.showLibrary = false; ui.workbenchChart = 'flow'; ui.pinnedChart = null;
  openProject(p.id);
  const n = p.pages.flatMap(pg => pg.nodes).find(n => moduleOf(n).kind === 'valve');
  if (n) {
    p.activePage = p.pages.find(pg => pg.nodes.includes(n)).id;
    openDevice(n.id);
    const f = ui.floats.find(f => f.id === n.id);
    f.tab = 'overview'; f.docked = innerWidth >= 1000; rememberWindow(f);
  }
  fitNetwork();
  saveUI(); render();
  msg('先运行或单步，再修改开度、应用参数，观察底部两条支路的曲线。');
}

let deviceWindowsController;
function deviceWindows(){return deviceWindowsController ||= FluidNetDeviceWindows.create({
  windows:{list:()=>ui.floats,replace:value=>{ui.floats=value;},front:()=>ui.frontId,focus:id=>{ui.frontId=id;return ++ui.floatSerial;},route:()=>ui.route,select:id=>{ui.selectedNode=id;},project:()=>state.activeProject},
  storage:{read:(projectId,id)=>state.windowPositions?.[projectId+':'+id],write:(projectId,id,value)=>{state.windowPositions||={};state.windowPositions[projectId+':'+id]=value;}},
  elements:{root:()=>root,page:()=>page,layer:()=>document.getElementById('floating-layer'),dock:()=>document.getElementById('inspector-dock'),viewport:()=>({width:innerWidth,height:innerHeight})},
  content:{node:instance,body:floatBody,footer:deviceWindowFooter,extras:deviceWindowExtras},chrome:{esc,icon,ibtn},
  effects:{dirty:markDirty,selection:syncDeviceSelection,message:msg,retainFocus,rendered:()=>{syncWorkbenchStatus();requestAnimationFrame(()=>{resizeCharts();restoreChartCursor();});}}
});}
function isDocked(f){return deviceWindows().isDocked(f);}
function syncDockLayout(){return deviceWindows().syncDockLayout();}
function dockWindowBounds(){return deviceWindows().dockBounds();}
function toggleDeviceDock(id){return deviceWindows().toggleDock(id);}

function chartDockChoices() {
  const bindings=overviewSeries(project().run);
  return [['flow', '设备流量'], ...['pressure','temperature'].filter(key=>bindings[key]).map(key=>[key,bindings[key].label])]
    .concat(state.charts.extra.filter(v => v.projectId === project().id).map(v => [v.id, v.label]));
}

function workbenchChartData() {
  const run = project().run;
  const bindings=overviewSeries(run);
  if (!chartDockChoices().some(([id]) => id === ui.workbenchChart)) ui.workbenchChart = 'flow';
  const key = ui.workbenchChart;
  if (key === 'flow') return { history: run.history, keys: ['q', 'a', 'b'].filter(key=>bindings[key]) };
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
  if (history.length < 2) return `<div class="dock-empty">${icon('Activity')}<strong>还没有可观察的曲线</strong><span>点击右侧“运行”或“单步”，这里将同步显示当前项目的计算结果。</span></div>`;
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
    <div class="dock-chart-meta"><span data-result-status></span><div class="chart-legend">${(ui.workbenchChart === 'flow' ? workbenchChartData().keys : []).map(k => `<button data-action="toggle-series" data-value="${k}" aria-pressed="${state.charts.series[k] !== false}" class="${state.charts.series[k] === false ? 'off' : ''}"><span class="series-key ${SERIES[k].color}"></span>${SERIES[k].short}</button>`).join('')}</div></div>
    <div id="workbench-chart-plot">${workbenchChartMarkup()}</div>
    <div class="dock-readout"><span id="workbench-flow-chart-readout">${workbenchChartReadout()}</span>${btn('release-cursor', '恢复实时读数', 'RefreshCw', `${ui.pinnedChart === 'workbench-flow-chart' ? '' : 'hidden'}`, 'ghost small')}</div>
    <div class="dock-event" data-workbench-event title="${esc(event?.text || '')}">${event ? `${clockLabel(event.t)} · ${esc(event.text)}` : '点击曲线可固定读数；参数应用时刻会显示为竖向虚线。'}</div>
  </section>`;
}

function refreshWorkbenchChart() {
  const plot = document.getElementById('workbench-chart-plot');
  if (!plot) return;
  FluidNetSvgDom.patch(plot,workbenchChartMarkup());
  const readout = document.getElementById('workbench-flow-chart-readout');
  if (readout) readout.textContent = workbenchChartReadout();
  restoreChartCursor();
}

function syncWorkbenchStatus() {
  const result = workbenchResultState();
  root.querySelectorAll('[data-result-status]').forEach(el => { el.textContent = result.text; el.className = 'result-status ' + result.tone; });
  for (const f of ui.floats) { const n=instance(f.id), shell=root.querySelector(`[data-float-id="${f.id}"]`); if(n&&shell)devicePanelView().refresh(shell,n); }
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
  return `<div class="page-shell">${heading('模块库', '定义可复用的设备：图形、端口、通路、变量与算法。', btn('nav', '节点定义', 'Waypoints', 'data-route="nodes"') + btn('equipment-library','设备组与选型','Boxes','','small')+btn('performance-library','性能资料库','Database','','small')+btn('new-module', '新建模块', 'Plus', '', 'primary'))}
    <div class="split-view">${moduleGroupSidebar()}<div class="module-content">
      ${ui.category === '倍思鹿参考模块' ? `<div class="notice module-reference-note">${icon('Info')}<span>来自倍思鹿参考实现，L1/L2/L3 验证状态见文档。</span></div>` : ''}
      ${ui.category !== '全部模块' ? `<div class="module-group-context"><div class="grow"><h2>${esc(ui.category)}</h2><small>${custom ? '自建分组' : '内置分类'} · ${members.length} 个模块</small></div>${custom ? btn('rename-module-group', '重命名', 'Pencil', `data-value="${esc(ui.category)}"`, 'small') + btn('delete-module-group', '删除分组', 'Trash2', `data-value="${esc(ui.category)}" ${members.length ? 'disabled title="请先将组内模块移到其他分组"' : ''}`, 'small') : ''}</div>` : ''}
      <div class="filterbar"><label class="search">${icon('Search')}<input data-filter="moduleSearch" aria-label="搜索模块" placeholder="名称或模块标识" value="${esc(ui.moduleSearch)}"></label><span class="push muted">${list.length} 个模块</span><div class="segmented" role="group" aria-label="模块库视图">${[['cards', '卡片视图', 'Grid2X2'], ['list', '紧凑列表', 'List']].map(([value, label, glyph]) => `<button data-action="module-view" data-value="${value}" aria-label="${label}" title="${label}" aria-pressed="${ui.moduleView === value}" class="${ui.moduleView === value ? 'active' : ''}">${icon(glyph)}</button>`).join('')}</div>${btn('compile-preview', '批量检查预览', 'CheckCheck', '', 'small')}</div>
      <div id="module-results" class="module-grid${ui.moduleView === 'list' ? ' module-compact-list' : ''}">${list.map(m => `<article class="module-card" data-module-id="${m.id}"><div class="row module-card-title"><span class="object-icon">${icon(m.icon)}</span><div class="grow"><h3>${esc(m.name)}</h3><small class="muted mono">${esc(m.code)}</small></div>${isReferenceModule(m) ? badge('参考模块', 'good') : ''}${badge(m.runtime === 'python' ? (m.publishedManifest ? 'Python · v'+m.publishedManifest.version : 'Python · 未发布') + (m.dirty?' · 有草稿':'') : '内置 · v'+m.version,m.runtime === 'python' ? 'blue' : '')}</div><button class="module-group-chip" data-action="move-module-group" data-id="${m.id}" aria-label="调整 ${esc(m.name)} 的分组" title="调整所属分组">${icon('Folder')}<span>${esc(m.category)}</span>${icon('ChevronDown')}</button><p>${esc(m.description)}</p>${moduleEvidenceSummary(m)}<div class="stat-line"><span>${(m.parameters || PARAM_DEFS[m.kind] || []).length} 个参数</span><span>${m.ports.length} 个端口</span><span>${m.channels.length} 条通路</span><span>${m.variables.length} 个变量</span></div><div class="card-footer">${isReferenceModule(m)||FluidNetDeviceGuide.get(m) ? btn('module-doc', '说明', 'BookOpen', `data-id="${m.id}"`, 'small') : ''}${btn('edit-module', '编辑模块', 'Pencil', `data-id="${m.id}"`, 'small')}${m.runtime === 'python' ? btn('test-module','独立验证','CheckCheck',`data-id="${m.id}"`,'small') + (m.manifest?.execution_role ? '' : btn('module-example',m.manifest?.sdk?.capabilities?.includes('composite.refrigeration.open.v1')?'宿主验收':'管网算例','Network',`data-id="${m.id}"`,'small')) : ''}<span class="push"></span>${ibtn('insert-module', '插入项目 ' + m.name, 'Plus', `data-id="${m.id}"`)}</div></article>`).join('') || (blankGroup ? empty('分组已建好，添加第一个模块', '可在此分组中新建模块，也可从“全部模块”的模块卡片调整所属分组。', btn('new-module', '在此分组新建模块', 'Plus', '', 'primary')) : empty('没有匹配的模块', '尝试其他分类或关键词。'))}</div>
    </div></div></div>`;
}

function openModuleDoc(id) {
  const m = state.modules.find(item => item.id === id);
  if (!m) throw Error('模块不存在或已从目录中移除。');
  const manifest = m.manifest || (m.runtime!=='python'&&engine.catalog?.modules.find(d=>d.id===m.kind)) || {};
  const parameters = manifest.parameters || m.parameters || [], ports = m.ports || manifest.ports || [];
  const variables = manifest.variables || [], channels = manifest.channels || m.channels || [];
  const text = value => value && typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—');
  const display=(p,value)=>value==null?'—':text(projectModel.toDisplay(p,value));
  const parameterUnit = p => p.unit?.display_unit || p.unit?.canonical_unit || '—';
  const table = (heads, rows) => `<div class="table-wrap"><table><thead><tr>${heads.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const section = (title, note, heads, rows) => rows.length ? `<section class="module-doc-section"><h3>${esc(title)}<small>${esc(note)}</small></h3>${table(heads, rows)}</section>` : '';
  const body = `${FluidNetDeviceGuide.markup(m,esc,true)}${section('参数', `${parameters.length} 项 · 按显示单位列出默认值和范围`, ['参数标识', '参数名称', '默认值', '单位', '范围', '修改时机'], parameters.map(p => [p.id, p.label || p.id, display(p,p.default), parameterUnit(p),p.value_type==='number'?display(p,p.minimum)+' ~ '+display(p,p.maximum):'—',p.writable===false?'只读':p.runtime?'运行中可调':'运行前可调']))}
    ${section('端口', `${ports.length} 个`, ['标识', '名称', '物理类型', '方向'], ports.map(p => [p.id, p.label || p.id, DOMAINS[p.domain||'fluid']?.label||p.domain, ({in:'输入',out:'输出',bidirectional:'双向'})[p.direction] || '—']))}
    <details class="editor-advanced-details"><summary>变量与内部通路</summary>${section('变量', `${variables.length} 个`, ['id', 'label', 'source', '单位'], variables.map(v => [v.id, v.label || v.id, v.source || '—', v.unit?.display_unit || v.unit?.canonical_unit || '—']))}
    ${section('通路', `${channels.length} 条`, ['id', 'relation', 'solver_model'], channels.map(c => [c.id, c.relation || c.kind || '—', c.solver_model || manifest.solver_model || '—']))}<p class="module-doc-hint">参考模块的映射和验证记录见 docs/MODULE_KIT.md、docs/MAPPING_A.md、docs/MAPPING_C.md。</p></details>`;
  openDialog(`${m.name} · v${m.version} · ${m.category}`, m.description || FluidNetDeviceGuide.get(m)?.summary || '参考模块说明', body, null, '', true);
}

// 画布操作与模块定义共用端口 / 通路，不根据图形猜测内部连接。
function deviceToolsMarkup(n) {
  if (!n) return '';
  return `<div class="device-tools" role="toolbar" aria-label="选中设备操作"><strong>${esc(n.id)} · ${esc(n.name)}</strong>${ibtn('device-overview', '设备总览', 'Gauge', `data-id="${n.id}"`)}${ibtn('open-device', '参数与型号', 'SlidersHorizontal', `data-id="${n.id}"`)}${ibtn('device-variables', '查看全部变量', 'Table2', `data-id="${n.id}"`)}${ibtn('choose-device-model', '选择设备型号', 'Database', `data-id="${n.id}"`)}${ibtn('rotate-device', '顺时针旋转 90° · R', 'RotateCw', `data-id="${n.id}"`)}${ibtn('rotate-device', '逆时针旋转 90° · Shift+R', 'RotateCcw', `data-id="${n.id}" data-direction="-1"`)}${ibtn('device-definition', '查看模块定义', 'Box', `data-id="${n.id}"`)}${ibtn('move-device-page','移到其他画布','Layers',`data-id="${n.id}"`)}</div>`;
}
let workbenchRefreshController;
function refreshWorkbench(){
  workbenchRefreshController ||= FluidNetWorkbenchRefresh.create({root,project,page:activePage,ui,viewBox:networkViewBox,canvas:canvasView,
    selection:()=>syncDeviceSelection(false),chartMarkup:renderWorkbenchChart,chartRefresh:refreshWorkbenchChart,chrome:syncChrome,icon,
    history:action=>action==='undo'?undoStack.length:redoStack.length,placingName:()=>mod(ui.placing).name,
    layout:()=>{syncDockLayout();requestAnimationFrame(()=>{resizeCharts();restoreChartCursor();});}});
  if(!workbenchRefreshController.refresh())render();
}
function syncDeviceSelection(paint=true) {
  if (ui.route !== 'workbench') return;
  const n = activePage().nodes.find(n => n.id === ui.selectedNode);
  const props = document.getElementById('selected-properties'), tools = document.getElementById('canvas-device-tools');
  if(props){const html=propertiesMarkup(n);if(props._selectionMarkup!==html){props.innerHTML=html;props._selectionMarkup=html;}}
  if(tools){const html=deviceToolsMarkup(n);if(tools._selectionMarkup!==html){tools.innerHTML=html;tools._selectionMarkup=html;}}
  root.querySelectorAll('#network [data-node]').forEach(el=>el.classList.toggle('selected',el.dataset.node===n?.id||groupSelected().includes(el.dataset.node)));
  if(paint)canvasView().refresh();
}
function rotateDevice(id, direction = 1) {
  const n = activePage().nodes.find(n => n.id === id); if (!n) return;
  remember(); projectState.updateNode(project(),n,{rotation:((n.rotation || 0) + direction * 90 + 360) % 360});
  ui.selectedNode = n.id; markDirty(project()); render();
  root.querySelector(`#network [data-node="${n.id}"]`)?.focus({ preventScroll: true });
}
function setDeviceTab(f,tab){return deviceWindows().setTab(f,tab);}
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
  const bound=moduleOf(n),draft=state.modules.find(m=>m.id===n.moduleId);
  const variable=variableId && bound.variables.find(v=>v.id===variableId);
  const definition=bound.manifest || {id:bound.id,version:bound.version,ports:bound.ports,channels:bound.channels,variables:bound.variables};
  const {source,...contract}=definition,code=source?.runtime || bound.source?.runtime;
  const hash=definition.definition_hash || n.package?.definition_hash || bound.contentHash || '';
  const body=`<div data-bound-definition="${esc(bound.id)}" data-bound-version="${esc(bound.version)}"><p><strong>${esc(n.id)} · ${esc(bound.name)} · v${esc(bound.version)}</strong></p>${hash?`<p class="mono">${esc(hash)}</p>`:''}
    ${variable?`<section data-bound-variable="${esc(variable.id)}"><h3>${esc(variable.label)} · ${esc(variable.name)}</h3><pre class="code-preview">${esc(JSON.stringify(variable,null,2))}</pre></section>`:''}
    <details ${variable?'':'open'}><summary>绑定版本合同</summary><pre class="code-preview">${esc(JSON.stringify(contract,null,2))}</pre></details>
    ${code?`<details><summary>绑定版本源码</summary><pre class="code-preview">${esc(code)}</pre></details>`:''}
    <div class="row wrap">${btn('close-dialog','返回设备','ArrowLeft','','small')}${draft?btn('edit-device-library',`编辑模块库草稿 · v${draft.version}`,'Pencil',`data-id="${esc(n.id)}" data-variable="${esc(variableId||'')}"`,'small'):''}</div></div>`;
  openDialog(`设备绑定定义 · ${n.id} · v${bound.version}`,'只读查看此项目实际使用的版本；模块库草稿独立编辑，发布和升级后才改变项目绑定。',body,null,'',true);
}
function editDeviceLibrary(id, variableId) {
  const n=instance(id);if(!n)return;
  if(!state.modules.some(m=>m.id===n.moduleId))throw Error('模块库中没有此草稿，请先从绑定版本建立模块草稿。');
  const origin = { projectId: project().id, pageId: activePage().id, nodeId: id, variableId };
  if (variableId) ui.variableSearch = moduleOf(n).variables.find(v => v.id === variableId)?.name || '';
  closeDialog();
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
  return FluidNetPathTrace.channels(moduleOf(n));
}
function internalChannelsMarkup(n) {
  const m = moduleOf(n);
  return `<g transform="rotate(${n.rotation || 0})" class="internal-channels" aria-hidden="true">${internalChannels(n).map(c => {
    const a = portOffset(n, m.ports.find(p => p.id === c.input)), b = portOffset(n, m.ports.find(p => p.id === c.output)), mid = (a.x + b.x) / 2;
    return `<path class="internal-channel" data-channel-id="${esc(c.id)}" data-channel-input="${esc(c.input)}" data-channel-output="${esc(c.output)}" d="M ${a.x} ${a.y} C ${mid} ${a.y}, ${mid} ${b.y}, ${b.x} ${b.y}"/>`;
  }).join('')}</g>`;
}
function showCanvasInspection(target) {
  if (target?.closest?.('#canvas-inspection')) return;
  const node = target?.closest?.('#network [data-node]'), port = target?.closest?.('[data-port-node]');
  // Keep a port trace while crossing the canvas to its navigation controls.
  if (!node && target?.closest?.('#network-area') && ui.canvasInspection?.portId) return;
  if (node?.dataset.node === ui.canvasInspection?.id && !port && ui.canvasInspection?.portId) return;
  const next = node ? { id: node.dataset.node, portId: port?.dataset.portId } : null;
  if (next?.id === ui.canvasInspection?.id && next?.portId === ui.canvasInspection?.portId && !document.getElementById('canvas-inspection')?.hidden) return;
  ui.canvasInspection = next;
  paintCanvasInspection();
}
function paintCanvasInspection() {
  const hint = document.getElementById('canvas-inspection'); if (!hint) return;
  const selected = ui.canvasInspection;
  const n = activePage().nodes.find(n => n.id === selected?.id);
  const trace = n && FluidNetPathTrace.describe(project(), n.id, selected.portId, moduleOf);
  root.querySelectorAll('.inspecting,.channel-active,.path-trace-active,.path-trace-remote').forEach(el =>
    el.classList.remove('inspecting','channel-active','path-trace-active','path-trace-remote'));
  hint.hidden = !trace;
  if (!trace) { hint.replaceChildren();delete hint.dataset.traceSignature;return; }
  const nodes = [...root.querySelectorAll('#network [data-node]')];
  const node = nodes.find(el => el.dataset.node === n.id); node?.classList.add('inspecting');
  node?.querySelectorAll('[data-channel-id]').forEach(el => el.classList.toggle('channel-active',trace.channels.some(c => c.id === el.dataset.channelId)));
  root.querySelectorAll('#network [data-port-node]').forEach(el => {
    const local = el.dataset.portNode === n.id && trace.ports.some(p => p.id === el.dataset.portId);
    const remote = trace.connections.some(c => c.valid && c.remote[0] === el.dataset.portNode && c.remote[1] === el.dataset.portId);
    el.classList.toggle('path-trace-active',local);el.classList.toggle('path-trace-remote',remote);
  });
  root.querySelectorAll('#network [data-trace-edge],.cross-page-strip [data-action="jump-page-link"]').forEach(el =>
    el.classList.toggle('path-trace-active',trace.connections.some(c => c.valid && c.id === (el.dataset.traceEdge || el.dataset.id))));
  const signature=JSON.stringify(trace);
  if(hint.dataset.traceSignature!==signature) {
    hint.innerHTML=FluidNetPathTrace.markup(trace,esc);hint.dataset.traceSignature=signature;
  }
  // A trace may appear during the first click of a double-click. Keep its whole
  // scrollable panel and navigation controls clear of the inspected device.
  hint.style.left='';hint.style.right='';hint.style.top='';hint.style.bottom='';
  const deviceBox=node?.getBoundingClientRect(),area=document.getElementById('network-area');
  if(deviceBox&&area){
    const areaBox=area.getBoundingClientRect(),panelBox=hint.getBoundingClientRect();
    const overlaps=(left,top)=>Math.max(0,Math.min(left+panelBox.width,deviceBox.right+8)-Math.max(left,deviceBox.left-8))
      *Math.max(0,Math.min(top+panelBox.height,deviceBox.bottom+8)-Math.max(top,deviceBox.top-8));
    const candidates=[
      {left:panelBox.left,top:panelBox.top},
      {left:areaBox.right-panelBox.width-56,top:panelBox.top},
      {left:areaBox.left+8,top:areaBox.top+50},
      {left:areaBox.right-panelBox.width-56,top:areaBox.top+50},
    ];
    const best=candidates.reduce((a,b)=>overlaps(b.left,b.top)<overlaps(a.left,a.top)?b:a);
    if(best!==candidates[0]){
      hint.style.left=`${best.left-areaBox.left}px`;hint.style.top=`${best.top-areaBox.top}px`;
      hint.style.right='auto';hint.style.bottom='auto';
    }
  }
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
  return [...owner.pages.flatMap(pg => pg.nodes).flatMap(n => moduleOf(n).variables.map(v => variableObservation(n, v, owner)).filter(Boolean)),
    ...(owner.measurements||[]).map(m=>({id:'measurement.'+m.id,identifier:'measurement.'+m.id,nodeId:'measurement',variableId:m.id,sampleKey:'measurement.'+m.id,name:m.label,device:'测点',origin:'measurement',writable:false,unit:m.unit.display_unit,value:panelRow(owner.run)?.canonical?.['measurement.'+m.id]}))];
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
let equipmentSelection;
let deviceBatchEditor;
function openDeviceBatch() {
  deviceBatchEditor ||= DeviceBatchEditor.create({getState:()=>state,project,moduleOf,engine,deviceParamSpecs,openDialog,closeDialog,esc,msg});
  deviceBatchEditor.open();
}
let equipmentLibrary;
function openEquipmentLibrary(){
  equipmentLibrary ||= createEquipmentLibrary({engine,getState:()=>state,replaceState:replaceWorkspaceState,emptyRun,uid,openDialog,esc,msg,navigate,persist:persistLocal,dirty:markDirty});
  equipmentLibrary.open().catch(e=>msg(e.message,true));
}
let performanceLibrary;
function openPerformanceLibrary(id){
  performanceLibrary ||= FluidNetPerformanceData.create({engine,getState:()=>state,project,instance,moduleOf,ownerOfInstance,
    openDialog,esc,msg,download:downloadFile,persist:persistLocal,dirty:markDirty,renderFloats});
  performanceLibrary.open(id).catch(e=>msg(e.message,true));
}
function openEquipmentSelection(id) {
  equipmentSelection ||= EquipmentSelection.create({esc,openDialog,instance,moduleOf,ownerOfInstance,
    engine,getState:()=>state,uid,markDirty,persist:persistLocal,renderFloats,msg});
  equipmentSelection.open(id);
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
      const definition=m.manifest||engine.catalog.modules.find(d=>d.id===m.kind);
      for(const spec of deviceParamSpecs(n).filter(p=>p.value_type!=='number')){
        if(fields.source.startsWith('bank:'))throw Error('此设备含曲线/文本参数，请选择当前值或待应用草稿保存完整型号。');
        params[spec.id]=clone((fields.source==='draft'?n.draft:n.params)[spec.id]??spec.default);
      }
      const performanceData=FluidNetPerformanceData.references(n,definition,params,fields.source==='draft'?'draft':'current');
      const sourceLabel = `${n.id} · ${sources.find(([key]) => key === fields.source)[1]}`, note = `从 ${project().name} / ${sourceLabel} 保存`;
      state.models.push({ id: uid('model'), moduleId: m.id, name, description: note, sourceLabel, version: 1, moduleVersion: m.version,
        params, performanceData, values: clone(values), bank: fields.source.startsWith('bank:') ? Number(fields.source.slice(-1)) + 1 : 1, archived: false,
        versions: [{ version: 1, note, params: clone(params), values: clone(values), performanceData:clone(performanceData) }] });
      markDirty(); retainFocus(renderFloats); msg('型号已保存，可在当前设备或同模块设备中选择应用。');
    }, '保存型号', true);
}
function modelVariableSummary(item) {
  const variables = mod(item.moduleId).variables.filter(v => v.origin === 'custom' && item.values?.[v.id] !== undefined);
  const sources=Object.values(item.performanceData||item.selection?.performanceData||{}).map(entry=>entry.provenance).filter(Boolean);
  return `${sources.length?`<div data-model-performance-source>保存时的性能资料：${sources.map(s=>`<p>${esc(s.name)} v${s.version} · ${esc(s.source)}</p>`).join('')}</div>`:''}${item.sourceLabel ? `<small class="muted">来源：${esc(item.sourceLabel)}</small>` : ''}${variables.length ? `<div class="model-variable-summary"><h3>自定义变量</h3><dl>${variables.map(v => `<dt>${esc(v.label)} <small>${esc(v.unit)}</small></dt><dd class="mono">${esc(variableDisplay(item.values[v.id], v, mod(item.moduleId).precision))}</dd>`).join('')}</dl></div>` : ''}`;
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
function paramsFields(kind, values, definitions = PARAM_DEFS[kind] || []) {
  return definitions.map(f => field(f[0], `${f[1]} · ${f[2]}`, values[f[0]] ?? f[6], `type="number" min="${f[3]}" max="${f[4]}" step="any" required`)).join('');
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
  openDialog(title, text, '', () => callback(), label);
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
    const f = moduleParamDefs(m).find(f => f[0] === v.param);
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
  const existing = existingId && model(existingId), m = existing ? engine.moduleForInsert(existing.moduleId) : mod();
  if(existing)EquipmentSelection.assertModelCompatible(existing,engine.manifestPayload(m));
  const definitions=m.parameterDefs || PARAM_DEFS[m.kind] || [];
  if (!existing) validateBank(m, m.banks[ui.bank]);
  const values = existing?.params || Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.banks[ui.bank]['param:' + f[0]]]));
  openDialog(existing ? '保存型号新版本' : '保存为设备型号', `${m.name} · ${existing ? '已插入的项目设备不会自动更新。' : `来源：库值 ${ui.bank + 1} · ${m.bankNames[ui.bank]}`}`, `<div class="fields">${field('name', '型号名称', existing?.name || `${m.name} · ${m.bankNames[ui.bank]}`, 'required maxlength="60"')}${field('description', '说明 / 版本备注', existing?.description || '', 'maxlength="160"')}${paramsFields(m.kind, values, definitions)}</div>`, data => {
    const name = data.name.trim(); if (!name) throw Error('型号名称不能为空。');
    if (state.models.some(v => v.id !== existingId && v.moduleId === m.id && v.name === name)) throw Error('此模块已有同名型号。');
    const params = {...clone(existing?.params||{}),...readParams(data, m.kind,'',definitions)}, note = data.description.trim() || '参数更新';
    if (existing) {
      existing.version++; existing.name = name; existing.description = note; existing.params = params;
      if (existing.values) for (const [key, value] of Object.entries(params)) existing.values['param:' + key] = value;
      existing.performanceData=FluidNetPerformanceData.references({performanceData:existing.performanceData||existing.selection?.performanceData},engine.manifestPayload(m),params);
      existing.versions.push({ version: existing.version, note, params: clone(params), performanceData:clone(existing.performanceData), ...(existing.values ? { values: clone(existing.values) } : {}) });
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
  EquipmentSelection.assertModelCompatible(item,engine.manifestPayload(moduleOf(n)));
  projectState.setDraft(ownerOfInstance(n),n,item.params); n.performanceDataDraft=clone(item.performanceData||item.selection?.performanceData||{}); projectState.updateNode(ownerOfInstance(n),n,{draftModelId:id,draftModelVersion:item.version});
  const data = ensureInstanceVariables(n);
  for (const v of moduleOf(n).variables.filter(v => v.origin === 'custom' && instanceWritable(v))) data.draft[v.id] = clone(item.values?.[v.id] ?? data.values[v.id]);
  markDirty(project());
}
function applyInstanceDialog(n) {
  const owner=ownerOfInstance(n);
  const values = instanceEdits(n);
  const application=instanceApplication(n,values);
  const rows = moduleOf(n).variables.filter(v => instanceWritable(v) && !sameValue(instanceVariableValue(n, v), values[v.id])).map(v => [`${v.label} · ${v.unit}`, instanceVariableValue(n, v), values[v.id]]);
  for (const p of deviceParamSpecs(n).filter(p => p.value_type !== 'number' && !sameValue(n.draft[p.id], n.params[p.id])))
    rows.push([`${p.label} · ${PARAM_TYPE_LABELS[p.value_type] || p.value_type}`, parameterValueText(n.params[p.id], p.value_type), parameterValueText(n.draft[p.id], p.value_type)]);
  if (n.draftModelId) rows.unshift(['来源型号', `${model(n.modelId)?.name || '自定义'} v${n.modelVersion || 1}`, `${model(n.draftModelId)?.name} v${n.draftModelVersion}`]);
  if(FluidNetPerformanceData.pending(n)){const labels=map=>Object.values(map||{}).map(entry=>entry.provenance.name+' v'+entry.provenance.version).join('；')||'无资料绑定';rows.unshift(['性能资料来源',labels(n.performanceData),labels(n.performanceDataDraft)]);}
  openDialog(`应用到 ${n.id} · ${n.name}`, '保存保留草稿；确认应用后参数生效，并在运行事件中记录时间。', diffMarkup(rows), async () => {
    try {
      await applyInstanceApplication(owner,n,application);
      owner.run.events.push({ t: owner.run.time, kind: 'parameters', text: `${n.id} 参数已应用：${rows.map(([label, , value]) => `${label}=${value}`).join('，')}` });
      msg(`${n.id} 参数已应用 · ${clockLabel(owner.run.time)}`);
    } catch(error) {msg(error.message,true);}
  }, '确认应用', true);
}
function windowBounds(f){return deviceWindows().bounds(f);}
function rememberWindow(f){return deviceWindows().remember(f);}
function openDevice(id){return deviceWindows().open(id);}
const PARAM_TYPE_LABELS = {number:'数值', boolean:'布尔', text:'文本', curve:'曲线'};
let devicePanel;
function configureDevicePanel(id=null) {
  const node=id?instance(id):null,owner=node?ownerOfInstance(node):null,m=node?moduleOf(node):mod();
  const specs=node?deviceParamSpecs(node):m.manifest?manifestParamSpecs(m.manifest):(PARAM_DEFS[m.kind]||[]).map(f=>({id:f[0],label:f[1],value_type:'number',minimum:f[3],maximum:f[4]}));
  // Library-era builtins obtain their fields from PARAM_DEFS; bind the same fields
  // that insertion freezes, otherwise a saved layout rejects its own new instance.
  const presentation=()=>m.manifest?m:{...m,parameterDefs:clone(moduleParamDefs(m))},editable=presentation();
  const before=JSON.stringify(FluidNetPanelLayout.binding(editable));
  FluidNetPanelLayout.editor({m:editable,specs,esc,openDialog:(title,description,...rest)=>openDialog(title,description+(owner?' 保存仅更新此项目同模块设备的面板。':' 保存作为此模块版本以后插入设备的默认面板，已有项目保留原布局。'),...rest),onSave:layout=>{
    if(JSON.stringify(FluidNetPanelLayout.binding(presentation()))!==before)throw Error('模块版本或字段已变化，请重新配置。');
    if(owner){
      projectState.assertCurrent(state,owner);projectState.node(owner,node);
      if(moduleOf(node)!==m)throw Error('项目模块已变化，请重新配置。');
      owner.moduleSnapshots||={};owner.moduleSnapshots[m.id]={...clone(editable),frozen:true};
      if(layout)owner.moduleSnapshots[m.id].panelLayout=layout;else delete owner.moduleSnapshots[m.id].panelLayout;
      markDirty(owner);
    }else{
      if(!state.modules.includes(m))throw Error('模块已被替换，请重新配置。');
      for(const p of state.projects)if(p.pages.some(pg=>pg.nodes.some(n=>n.moduleId===m.id))&&!p.moduleSnapshots?.[m.id]){
        p.moduleSnapshots||={};p.moduleSnapshots[m.id]={...clone(m),frozen:true};
      }
      if(!m.manifest)m.parameterDefs=clone(editable.parameterDefs);
      if(layout)m.panelLayout=layout;else delete m.panelLayout;
      markDirty();
    }
    persistLocal();render();msg('面板配置已保存；设备参数与物理模块版本保持原值。');
  }});
}
function devicePanelView() {
  return devicePanel ||= createDevicePanel({moduleOf, ownerOfInstance, instanceVariablesBody,
    esc, icon, btn, ibtn, badge, number, option, pendingCount, model, paramDefs, deviceParamSpecs,
    sameValue, parameterValueText, PARAM_TYPE_LABELS, DOMAINS, links, project, getState:()=>state,
    panelRow, parameterKey:projectParameterKey, observation:(n,v)=>engine.observation(n,v),
    observationButton:variableObservationButton,definitionOf:n=>moduleOf(n).manifest||engine.catalog?.modules.find(m=>m.id===moduleOf(n).kind)});
}
function floatBody(f,n) { return devicePanelView().body(f,n); }
function quickCanvasMarkup(n, m) {
  const def = paramDefs(n).find(f => f[0] === m.quickParam);
  if (!def || m.variables.find(v => v.param === def[0])?.display === false) return '';
  const value=n.params[def[0]],label=value!=null&&Number.isFinite(Number(value))?Number(value).toLocaleString('en-US',{maximumSignificantDigits:5}):'—';
  return `<g data-quick-node="${n.id}" role="button" tabindex="0" aria-label="修改 ${esc(n.name + ' ' + def[1])}"><title>${esc(def[1]+'：'+label+' '+def[2])}</title><rect class="quick-param" x="-35" y="68" width="70" height="20" rx="4"/><text class="quick-param-label" x="0" y="82" text-anchor="middle">${label} ${esc(def[2])}${m.quickType === 'display' ? '' : ' ▾'}</text></g>`;
}
function deviceWindowFooter(f,n){
  const bank=f.tab==='variables'?variableWindowState(f).source:-1;
  const apply=bank<0?btn('apply-instance','预览并应用','Check',`data-id="${n.id}" ${pendingCount(n)?'':'disabled'}`,'primary small')
    :btn('apply-instance-bank',`应用库值 ${bank+1}`,'Check',`data-id="${n.id}" data-bank="${bank}" ${instanceBankDiff(n,bank).length?'':'disabled'}`,'primary small');
  return `<footer class="float-footer"><div class="float-save-state grow"><small data-float-save>${state.dirty?'草稿未保存':'草稿已保存'}</small><small data-float-keyframe ${replayingKeyFrame(project().run)?'':'hidden'}>回放：显示最近关键帧</small><small data-device-apply-status="${n.id}"></small></div>${btn('save','保存草稿','Save','title="保存整个原型；待应用参数保持草稿状态"','small')}${apply}</footer>`;
}
function taskDrawerMarkup(){return `<section class="task-drawer"><div class="panel-head"><h3>运行任务</h3>${ibtn('tasks','关闭任务列表','X')}</div><div class="panel-body stack">${state.projects.filter(p=>['running','paused'].includes(p.run.status)).map(p=>`<div class="row"><div class="grow"><strong>${esc(p.name)}</strong><small>${statusText(p.run)} · ${clockLabel(p.run.time)}</small></div>${btn('open-project','查看','',`data-id="${p.id}"`,'small')}${btn('stop-task','停止','',`data-id="${p.id}"`,'small')}</div>`).join('')}<small class="muted">切换页面或关闭查看窗口后，任务继续保留。</small></div></section>`;}
function refreshTaskDrawer(){const drawer=root.querySelector('.task-drawer');if(drawer&&ui.taskDrawer)FluidNetSvgDom.update(drawer,taskDrawerMarkup());}
function deviceWindowExtras(){
  let html='';
  if(contextMenu)html+=`<div class="context-menu" style="left:${contextMenu.x}px;top:${contextMenu.y}px">${deviceContextMarkup(contextMenu.id)}</div>`;
  if(ui.taskDrawer)html+=taskDrawerMarkup();
  return html;
}
function renderFloats(){return deviceWindows().render();}
function updateFloatBodies(){return deviceWindows().updateBodies();}
async function setBench(id, params) {
  if (['running', 'solving'].includes(state.bench.run.status)) throw Error('先停止当前单机测试，再切换被测设备。');
  const m = mod(id);
  if(m.contractDraft !== undefined && !await engine.checkModule(m,true)) { msg('契约未通过校验，请先修正。',true); return; }
  moduleReplay?.close();
  state.bench.moduleId = m.id;
  const conditions=m.testConditions || ModuleTestEditor.defaultConditions(m.manifest || {});
  state.bench.boundary={inlet:(conditions.inlet_pressure_pa ?? 250000)/1000,
    outlet:(conditions.outlet_pressure_pa ?? 120000)/1000,temperature:(conditions.temperature_k ?? 293.15)-273.15,
    fluid:conditions.fluid?.fluid || 'Ammonia'};
  state.bench.params = params ? clone(params)
    : m.runtime === 'python' ? manifestParamDefaults(m.manifest)
    : Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.values['param:' + f[0]] ?? f[6]]));
  state.bench.run = emptyRun('bench');
  state.bench.run.step = Math.max(.01, (m.values['system:step'] || 100) / 1000);
  markDirty(); navigate('bench');
}
async function createModuleExample(id) {
  const m=engine.moduleForInsert(id), channel=m.channels.find(c=>c.enabled);
  if(m.manifest.sdk?.capabilities?.includes('composite.refrigeration.open.v1')) {
    if(state.projects.length>=20)throw Error('项目数量已达到上限。');
    const conditions=state.modules.find(module=>module.id===id)?.testConditions;
    if(!conditions?.host_project)throw Error('开放设备组需要真实宿主回路；请在已连接的制冷项目中重新封装，或把本组插入项目并连接所有公开端口。');
    const owner=state,host=clone(conditions.host_project),target=host.instances.find(n=>n.id===(conditions.host_instance_id || 'D1'));
    if(!target || target.module_id!==id)throw Error('宿主工况与此设备组不匹配，请重新封装。');
    host.modules=host.modules.filter(definition=>definition.id!==id).concat([engine.manifestPayload(m)]);
    target.parameters={};target.draft_parameters={};target.package=null;target.model_id=null;target.model_version=null;
    host.name=m.name+' · 宿主验收';
    const doc=await engine.exchangeDocument(host);
    if(state!==owner)throw Error('工作区已变化，请重新创建宿主验收项目。');
    doc.project.id=uid('project');doc.project.solver.duration=1;doc.project.solver.dt=conditions.dt_s || .1;
    replaceWorkspaceState(projectState.mergeDocument(owner,doc,emptyRun));markDirty();persistLocal();openProject(doc.project.id);return;
  }
  if(m.manifest.execution_role)throw Error('制冷模块请插入集总制冷站，连接上游饱和容器液相出口与下游压力等级。可先使用独立验证台检查开度特性。');
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
    p.solver.duration=1;p.solver.dt=.1;projectState.addProject(state,p);normalizeState();markDirty(p);openProject(p.id);return;
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
  projectState.addProject(state,p); normalizeState(); markDirty(p); ui.showLibrary=true; openProject(p.id);
}
function useModuleDialog(moduleId) {
  const workspace=state,m=state.modules.find(item=>item.id===moduleId);
  if(!m)throw Error('模块已不存在，请重新选择。');
  engine.moduleForInsert(moduleId);
  let displayedVersion='';
  const versionKey=plan=>JSON.stringify([plan.module.version,plan.module.manifest?.definition_hash,plan.module.manifest?.content_hash]);
  openDialog('放入项目',m.name+' · 选择项目和画布，添加后即可连接设备并调整参数。',
    '<div class="stack">'+selectField('project','目标项目',state.projects.map(p=>[p.id,p.name]),state.activeProject)+selectField('page','目标画布',[],'')+
    '<p id="module-insertion-version" class="notice" role="status"></p></div>',data=>{
      if(state!==workspace)throw Error('工作区已切换，请重新选择。');
      const owner=state.projects.find(p=>p.id===data.project);
      if(!owner)throw Error('目标项目已不存在，请重新选择。');
      const plan=engine.insertionPlan(owner,moduleId,data.page);
      if(versionKey(plan)!==displayedVersion){refresh();throw Error('可用版本已变化，请核对下方版本后重新添加。');}
      owner.activePage=data.page;openProject(owner.id);
      const node=newInstance(moduleId);openDevice(node.id);persistLocal();
      msg(`${m.name} 已放入 ${owner.name} / ${plan.page.name}${plan.module.runtime==='python'?' · v'+plan.module.version:''}。`);
    },'添加设备');
  const form=document.getElementById('dialog-form'),projectSelect=form.elements.project,pageSelect=form.elements.page;
  function refresh(){
    const owner=state.projects.find(p=>p.id===projectSelect.value),previous=pageSelect.value;
    pageSelect.innerHTML=(owner?.pages||[]).map(pg=>option(pg.id,pg.name,previous||owner.activePage)).join('');
    const status=form.querySelector('#module-insertion-version'),submit=form.querySelector('[type="submit"]');
    try {
      if(!owner)throw Error('目标项目已不存在，请重新选择。');
      const plan=engine.insertionPlan(owner,moduleId,pageSelect.value);displayedVersion=versionKey(plan);submit.disabled=false;
      status.textContent=plan.module.runtime!=='python'?'将使用此设备模块的参数默认值。':plan.usesPinnedVersion?
        `此项目固定使用 v${plan.module.version}，模块库已保存 v${plan.availableVersion}。本次添加 v${plan.module.version}；需要更新时可在项目的“模块版本”中统一升级。`:
        `将使用已保存的 v${plan.module.version}。当前模块草稿的算法和参数修改需保存新版本后再使用。`;
    }catch(error){displayedVersion='';submit.disabled=true;status.textContent=error.message;}
  }
  projectSelect.addEventListener('change',()=>{pageSelect.value='';refresh();});
  pageSelect.addEventListener('change',refresh);refresh();
}
function newInstance(moduleId, point, selectedModel) {
  const pg = activePage(), plan = engine.insertionPlan(project(),moduleId,pg.id);
  EquipmentSelection.assertModelCompatible(selectedModel,engine.manifestPayload(plan.module));
  remember();
  const m = engine.bindModule(project(),moduleId);
  const node = makeInstance(uid(m.kind === 'valve' ? 'V' : m.kind === 'pump' ? 'P' : 'D'), m.kind, m.name, point?.x ?? 250 + pg.nodes.length % 5 * 110, point?.y ?? 140 + Math.floor(pg.nodes.length / 5) * 100);
  node.moduleId = m.id;
  if (m.manifest) { node.params=manifestParamDefaults(m.manifest); node.draft=clone(node.params); }
  if (selectedModel) { node.params = clone(selectedModel.params); node.draft = clone(node.params); node.modelId = selectedModel.id; node.modelVersion = selectedModel.version; node.performanceData=clone(selectedModel.performanceData||selectedModel.selection?.performanceData||{}); }
  else if (m.id !== m.kind) { node.modelId = null; if (!m.manifest) { node.params = Object.fromEntries((PARAM_DEFS[m.kind] || []).map(f => [f[0], m.values['param:' + f[0]] ?? f[6]])); node.draft = clone(node.params); } }
  ensureInstanceVariables(node, m);
  if (selectedModel?.values) for (const v of m.variables.filter(v => v.origin === 'custom')) {
    const value = clone(selectedModel.values[v.id] ?? node.variableState.values[v.id]);
    node.variableState.values[v.id] = clone(value); node.variableState.draft[v.id] = clone(value); node.variableState.banks[0][v.id] = clone(value);
  }
  projectState.addNode(project(),pg.id,node); engine.pinProject(project()); ui.selectedNode = node.id; ui.placing = null; if (innerWidth <= 500) ui.showLibrary = false;
  // Default grid insertion must remain reachable when a large diagram exceeds the view.
  // Keep the current pan/zoom when the new symbol and its label already fit.
  const [vx,vy,vw,vh]=networkViewBox(pg).split(' ').map(Number);
  if(node.x-65<vx||node.x+65>vx+vw||node.y-65<vy||node.y+105>vy+vh)fitNetwork(pg);
  markDirty(project()); render(); return node;
}
function assertLinksIdle(owner=project()){
  if(owner.run.live || ['running','solving','paused'].includes(owner.run.status))throw Error('请先停止运行，再修改连接或移动设备；切换画布可直接进行。');
}
function jumpPageLink(id,nodeId){
  const owner=project(),edge=links.find(owner,id),target=links.locate(owner,nodeId);
  if(!edge || !target || ![edge[1],edge[3]].includes(nodeId))throw Error('跨页连接已失效，请检查连接列表。');
  closeDialog();owner.activePage=target.page.id;ui.connecting=null;ui.selectedNode=nodeId;ui.selectedEdge='';
  fitNetwork(target.page);render();openDevice(nodeId);
}
function pageLinksDialog(){
  const owner=project(),entries=links.cross(owner),errors=links.validate(owner,moduleOf,false);
  openDialog('跨页连接',owner.name,`<div class="stack">${btn('add-page-link','新建跨页连接','Plus','','primary')}${entries.map(link=>`<div class="list-row" data-page-link="${esc(link.edge[0])}"><div class="grow"><strong>${esc(link.localPage.name)} · ${esc(link.local.join(':'))}</strong><small>↔ ${esc(link.remotePage.name)} · ${esc(link.remote.join(':'))}</small></div>${ibtn('jump-page-link','跳到起点','ChevronLeft',`data-id="${esc(link.edge[0])}" data-node="${esc(link.local[0])}"`)}${ibtn('jump-page-link','跳到终点','ArrowRight',`data-id="${esc(link.edge[0])}" data-node="${esc(link.remote[0])}"`)}${btn('edit-page-link','修改','Pencil',`data-id="${esc(link.edge[0])}"`,'small')}${btn('delete-edge','断开','X',`data-id="${esc(link.edge[0])}"`,'small')}</div>`).join('')||'<p>暂无跨页连接。也可以在设备的“连接”页签选择跨页端口。</p>'}${errors.map(error=>`<p role="alert">${esc(error.text)}</p>`).join('')}</div>`,null,'',true);
}
function pageLinkDialog(nodeId,portId,edgeId,includeSamePage=false){
  assertLinksIdle();const owner=project(),existing=edgeId&&links.find(owner,edgeId);
  if(edgeId&&!existing)throw Error('连接已不存在，请重新打开。');
  if(existing){nodeId=existing[1];portId=existing[2];}
  const sources=owner.pages.flatMap(pg=>pg.nodes.flatMap(node=>moduleOf(node).ports
    .filter(port=>(!nodeId||(node.id===nodeId&&port.id===portId))&&!links.atPort(owner,node.id,port.id,edgeId))
    .map(port=>[node.id+':'+port.id,pg.name+' · '+node.id+' · '+port.label])));
  if(!includeSamePage&&owner.pages.length<2)throw Error('请先新增另一张画布。');
  if(!sources.length)throw Error('没有可用起点；请先断开已有连接。');
  closeDialog();
  openDialog(existing?'修改跨页连接':includeSamePage?'连接设备':'新建跨页连接',includeSamePage?'选择同一画布或其他画布上的设备；列表只显示兼容且空闲的端口。':'连接属于同一项目，跨页两端由同一次计算求解。',
    '<div class="stack">'+selectField('source','起点端口',sources,sources[0][0])+selectField('targetPage','目标画布',[], '')+selectField('target','目标端口',[], '')+'<p id="connection-hint" class="muted" role="status"></p></div>',data=>{
      if(project()!==owner)throw Error('项目已切换，请重新选择。');
      assertLinksIdle(owner);const source=data.source.split(':'),target=data.target.split(':');
      const start=links.locate(owner,source[0]),end=links.locate(owner,target[0]);
      if(!start||!end||(!includeSamePage&&start.page===end.page))throw Error('请选择有效的目标端口。');
      links.check(owner,source,target,moduleOf,edgeId);remember();
      projectState.connect(owner,edgeId||uid('edge'),source,target,moduleOf,!!edgeId);
      ui.connecting=null;markDirty(owner);persistLocal();render();msg('连接已保存到项目，重新运行后生效。');
    },existing?'应用修改':'建立连接');
  const form=document.getElementById('dialog-form'),sourceSelect=form.elements.source,pageSelect=form.elements.targetPage,targetSelect=form.elements.target;
  function refreshTargets(){
    const source=sourceSelect.value.split(':'),start=links.locate(owner,source[0]);
    const previous=pageSelect.value;
    pageSelect.innerHTML=owner.pages.filter(pg=>includeSamePage||pg!==start?.page).map(pg=>option(pg.id,pg.name,previous||links.locate(owner,existing?.[3])?.page.id||start?.page.id)).join('');
    const targets=links.candidates(owner,source,moduleOf,{pageId:pageSelect.value,excluding:edgeId});
    targetSelect.innerHTML=targets.map(({node,port})=>option(node.id+':'+port.id,node.name+' · '+node.id+' · '+port.label,existing?existing[3]+':'+existing[4]:'')).join('')||'<option value="">没有兼容的空闲端口</option>';
    form.querySelector('[type="submit"]').disabled=!targets.length;
    form.querySelector('#connection-hint').textContent=targets.length?'':'请先在目标画布放入相同物理类型的设备，或断开已占用的端口。';
  }
  sourceSelect.addEventListener('change',()=>{pageSelect.value='';refreshTargets();});
  pageSelect.addEventListener('change',refreshTargets);refreshTargets();
}
function moveDevicePage(id){
  assertLinksIdle();const owner=project(),found=links.locate(owner,id);
  if(!found)return;
  const targets=owner.pages.filter(pg=>pg!==found.page);
  if(!targets.length)throw Error('请先新增另一张画布。');
  openDialog('移动设备到其他画布','已有连接和变量引用会保留，跨页连接自动显示在两端画布。',selectField('page','目标画布',targets.map(pg=>[pg.id,pg.name]),targets[0].id),data=>{
    if(project()!==owner)throw Error('项目已切换，请重新选择。');assertLinksIdle(owner);
    const target=owner.pages.find(pg=>pg.id===data.page);
    if(!target||target.nodes.length>=64)throw Error('目标画布不存在或已达到设备上限。');
    remember();projectState.moveNode(owner,id,target.id);projectState.updateNode(owner,found.node,{x:150+(target.nodes.length-1)%5*160,y:150+Math.floor((target.nodes.length-1)/5)*150});
    fitNetwork(found.page);fitNetwork(target);owner.activePage=target.id;ui.selectedNode=id;ui.connecting=null;
    markDirty(owner);persistLocal();render();msg('设备已移动，已有连接保持不变。');
  },'移动设备');
}
function validateNetwork(p = project()) {
  const errors = links.validate(p, moduleOf);
  if (!p.pages.some(pg => pg.nodes.length)) errors.push({ text: '项目没有设备。' });
  for (const pg of p.pages) {
    for (const n of pg.nodes) {
      const m = moduleOf(n);
      for (const text of checkChannels(m)) errors.push({ text: `${n.id} · ${text}`, page: pg.id, node: n.id });
    }
  }
  return errors;
}
function connectPort(nodeId, portId) {
  assertLinksIdle();
  const owner = project(), next = globalEndpoint(owner, nodeId, portId);
  if (!next) return;
  const used = links.atPort(owner, nodeId, portId);
  if (used) throw Error('此端口已经连接。请先断开原连接，或使用连接节点分支。');
  if (!ui.connecting) { ui.connecting = { nodeId, portId }; refreshWorkbench(); return; }
  const first = ui.connecting;
  if (first.nodeId === nodeId) { ui.connecting = null; refreshWorkbench(); return; }
  const source = [first.nodeId, first.portId], target = [nodeId, portId];
  links.check(owner, source, target, moduleOf);
  remember(); projectState.connect(owner, uid('edge'), source, target, moduleOf); ui.connecting = null;
  markDirty(project()); render(); msg('连接已建立。');
}
function deleteNode(id) {
  assertLinksIdle();
  const owner=project(),pg=owner.pages.find(pg=>pg.nodes.some(n=>n.id===id));if(!pg)return;
  const references=coldStorage.couplingReferences(owner,[id]);
  const key=projectParameterKey(owner);
  if(references.length)coldStorage.assertCouplingIdle(owner);
  const remove=()=>{
    if(project()!==owner)throw Error('项目已切换，请重新选择要删除的设备。');
    if(projectParameterKey(owner)!==key)throw Error('确认期间项目发生变化，请重新选择要删除的设备。');
    const targetPage=owner.pages.find(page=>page.nodes.some(node=>node.id===id));
    if(!targetPage)throw Error('设备已不存在，请重新选择。');
    assertLinksIdle(owner);
    const couplingLinks=coldStorage.couplingReferences(owner,[id]);
    if(couplingLinks.length)coldStorage.assertCouplingIdle(owner);
    remember();projectState.removeNodes(owner,[id]);
    if(couplingLinks.length){
      const removed=new Set(couplingLinks.map(link=>link.id));
      owner.thermalCouplings=owner.thermalCouplings.filter(link=>!removed.has(link.id));
      coldStorage.syncCouplingCharts(owner);
    }
    ui.floats=ui.floats.filter(f=>f.id!==id);ui.selectedNode='';ui.connecting=null;
    markDirty(owner);persistLocal();render();msg(couplingLinks.length?'设备、关联连接与热耦合已删除，可撤销。':'设备与关联连接已删除，可撤销。');
  };
  if(references.length)confirmChange('删除热耦合设备',`删除 ${id} 将同时解除热耦合 ${references.map(link=>link.id).join('、')}。相关当前曲线也会移除，已保存运行记录保留。`,remove,'删除并解除耦合');
  else remove();
}
function deleteEdge(id) { assertLinksIdle(); remember(); projectState.removeConnection(project(),id); closeDialog(); ui.selectedEdge = ''; markDirty(project()); render(); }
function groupSelected(){return ui.multiProject===project().id?(ui.multiSelected||[]).filter(id=>instance(id)):[];}
function groupSelection(ids){ui.multiProject=project().id;ui.multiSelected=[...new Set(ids)];ui.selectedNode=ids.at(-1)||'';refreshWorkbench();}
function projectGroupTools(){
  const owner=project(),before=JSON.stringify(owner.pages),run=owner.run,selected=groupSelected();
  openDialog('设备组操作','Shift+单击切换多选；Shift+拖动空白处框选。复制保留内部连线，外部引用处理会在下一步预览。',
    `<label class="field"><span>操作</span><select name="group-action" aria-label="设备组操作">${[['copy','复制到画布'],['move','移动到画布'],['left','左对齐'],['top','顶对齐'],['horizontal','水平分布'],['vertical','垂直分布']].map(([k,v])=>option(k,v,'copy')).join('')}</select></label><label class="field"><span>目标画布</span><select name="group-page" aria-label="设备组目标画布">${owner.pages.map(g=>option(g.id,g.name,owner.activePage)).join('')}</select></label><div class="fields">${owner.pages.flatMap(g=>g.nodes.map(n=>`<label class="check-label"><input name="group-node:${esc(n.id)}" type="checkbox" aria-label="组选择 ${esc(n.id)}" ${selected.includes(n.id)?'checked':''}>${esc(g.name+' · '+n.id+' · '+n.name)}</label>`)).join('')}</div>`,data=>{
      projectState.assertCurrent(state,owner);if(owner.run!==run||JSON.stringify(owner.pages)!==before)throw Error('项目已变化，请重新选择');
      const ids=owner.pages.flatMap(g=>g.nodes).filter(n=>data['group-node:'+n.id]).map(n=>n.id),tools=FluidNetProjectEditing;
      tools.idle(owner);tools.select(owner,ids);
      if(data['group-action']==='copy'){
        const plan=tools.copy(owner,ids,data['group-page'],uid),frozen=JSON.stringify(owner);
        openDialog('复制设备组预览',`${ids.length} 台设备、${plan.edges.length} 条内部连线；${plan.external.length} 条外部连线不复制。`,
          `<div class="stack">${plan.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}<p>内部测点 ${plan.measurements.length}、完整热耦合 ${plan.couplings.length}、工质锚点 ${plan.circuits.length} 将按新ID复制。部分选中的关系保留原对象，副本需补齐后检查。</p><pre>${esc(JSON.stringify(plan.map,null,2))}</pre></div>`,()=>{
            projectState.assertCurrent(state,owner);if(JSON.stringify(owner)!==frozen)throw Error('预览后项目已变化');
            remember();const copied=tools.commitCopy(owner,plan);owner.activePage=plan.pageId;markDirty(owner);persistLocal();groupSelection(copied);msg('设备组已复制，请检查未连接端口及回路边界。');
          },'确认复制',true);
      }else{
        remember();if(data['group-action']==='move'){tools.move(owner,ids,data['group-page']);owner.activePage=data['group-page'];}
        else tools.align(owner,ids,data['group-action']);
        markDirty(owner);persistLocal();groupSelection(ids);msg('设备组操作已应用，可撤销。');
      }
    },'预览或应用',true);
}
function projectFind(){
  const owner=project();openDialog('全项目查找','按实例编号、名称、模块、画布或声明回路查找。',
    '<label class="field"><span>关键词</span><input data-project-find aria-label="全项目查找关键词"></label><div data-project-find-results></div>');
  const input=document.querySelector('[data-project-find]'),out=document.querySelector('[data-project-find-results]');
  const update=()=>{out.innerHTML=FluidNetProjectEditing.search(owner,input.value,moduleOf,engine.circuits(owner.id)||[]).map(({node,page})=>`<button type="button" class="btn ghost small" data-action="project-find-node" data-id="${esc(node.id)}" data-project="${esc(owner.id)}">${esc(page.name+' · '+node.id+' · '+node.name+' · '+moduleOf(node).name)}</button>`).join('')||'<p>没有匹配设备。</p>';};
  input.addEventListener('input',update);update();
}
function copyDevice(id = ui.selectedNode) { const n = instance(id); if (n) { ui.clipboard = clone(n); msg(`${n.id} 已复制；Ctrl+V 粘贴。`); } }
function pasteDevice() {
  if (!ui.clipboard) return;
  remember(); const n = clone(ui.clipboard); n.id = uid('D'); n.name += ' 副本'; n.x += 60; n.y += 60;
  projectState.addNode(project(),activePage().id,n); ui.selectedNode = n.id; markDirty(project()); render();
}
function commandRun(scope, command, projectId) { return engine.command(scope, command, projectId); }
function refreshLive(paintCanvas=true) {
  refreshTaskDrawer();
  coldStorage.refresh(project());
  airSide.refresh();
  const controlLive=document.getElementById('control-live');if(controlLive)controlLive.textContent=controlLiveValues();
  for(const m of project().measurements||[]){const el=document.querySelector(`[data-meter-value="${m.id}"]`);if(el)el.innerHTML=meterValue(project(),m);}
  for(const c of project().controllers||[]){const el=document.querySelector(`[data-pid-readout="${c.id}"]`);if(el)el.textContent=pidReadout(project(),c);}
  if (ui.route === 'curves') {
    const run = currentChartRun();
    const items = [['main-chart', ['q', 'a', 'b'], 'main-flow-chart'], ['pressure-chart', ['pressure'], 'pressure-line'], ['temperature-chart', ['temperature'], 'temperature-line']];
    for (const [id, keys, chartId] of items) { const e = document.getElementById(id); if (e) FluidNetSvgDom.patch(e,chartSvg(run.history, keys, chartId, id === 'main-chart' && state.charts.compare)); }
    updateExtraCharts();
    const readout = document.getElementById('main-flow-chart-readout');
    if (readout && !ui.pinnedChart) readout.textContent = `${clockLabel(run.time)} · 主管 ${number(run.values?.q ?? run.history.at(-1)?.q, 3)} kg/s`;
  }
  if (ui.route === 'workbench') refreshWorkbenchChart();
  restoreChartCursor();
  if (ui.route === 'workbench' && !workspaceInput?.busy()) {
    if(paintCanvas)canvasView().refresh(); paintCanvasInspection();
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
let apiContext=null;
function apiRunId(owner=project()) { return owner.run.runId||owner.run.id; }
function apiContextCurrent(context) {
  return apiContext===context && project()===context.owner && context.owner.run===context.run && apiRunId(context.owner)===context.id;
}
function apiCall(kind=ui.apiKind||'read') {
  const context=apiContext;
  if(!context || !apiContextCurrent(context) || !context.items)throw Error('先运行项目并等待变量目录载入。');
  const items=context.items.filter(v=>kind!=='set'||v.writable);
  const selected=items.find(v=>v.key===context.selected[kind])||items[0];
  const value=kind==='set' ? JSON.parse(document.getElementById('api-write-value')?.value||JSON.stringify(selected?.value??null)) : undefined;
  return FluidNetApiExamples.request(context.id,kind,selected,value);
}
function apiPreview(kind=ui.apiKind||'read',response=null) {
  const owner=project(),id=apiRunId(owner),target=document.getElementById('api-target');
  if(!target)return;
  if(!apiContext || !apiContextCurrent(apiContext)) {
    const context=apiContext={owner,run:owner.run,id,selected:{},items:null,error:''};
    if(id)Promise.all([engine.request(`/runs/${encodeURIComponent(id)}`),engine.request(`/runs/${encodeURIComponent(id)}/variables`).catch(error=>{if(error.detail?.code==='NO_FRAME')return {values:{}};throw error;})])
      .then(([record,sample])=>{if(!apiContextCurrent(context))return;context.items=FluidNetApiExamples.directory(record,sample.values);apiPreview();})
      .catch(error=>{if(!apiContextCurrent(context))return;context.error=error.message;apiPreview();});
  }
  const context=apiContext,output=document.getElementById('api-response'),path=document.getElementById('api-path'),request=document.getElementById('api-request'),button=root.querySelector('[data-action="api-preview"]');
  if(!context.items) {
    target.textContent=context.error||(!id?'先运行项目，生成运行编号。':'正在读取当前运行的变量目录…');
    path.textContent='';request.textContent='';output.textContent='';button.disabled=true;return;
  }
  const items=context.items.filter(v=>kind!=='set'||v.writable),selected=items.find(v=>v.key===context.selected[kind])||items[0];
  context.selected[kind]=selected?.key;
  target.innerHTML=kind==='status'?'':`<label class="field"><span>${kind==='set'?'写入参数':'读取／订阅变量'} · 引擎单位</span><select data-api-variable aria-label="接口变量" ${items.length?'':'disabled'}>${items.map(v=>option(v.key,`${v.label||v.key} · ${v.key}${v.unit?' ('+v.unit+')':''}`,selected?.key)).join('')}</select></label>${kind==='set'&&selected?`<label class="field"><span>写入值（JSON） · ${esc(selected.unit||'无量纲')}</span><input id="api-write-value" data-api-write aria-label="接口写入值" value="${esc(context.writeValues?.[selected.key]??JSON.stringify(selected.value))}"></label>`:''}`;
  try {
    const call=apiCall(kind),auth=engine.health?.auth?.required?' -H "Authorization: Bearer $FLUIDNET_TOKEN"':'';
    path.textContent=call.path;path.previousElementSibling.textContent=call.method;
    request.textContent=call.method==='WS'
      ? `${location.protocol==='https:'?'wss':'ws'}://${location.host}${call.path}${engine.health?.auth?.required?'\n# 浏览器连接使用子协议 fluidnet.bearer.<令牌>':''}`
      : `curl${auth}${call.body?` -H "Content-Type: application/json" -d '${JSON.stringify(call.body)}'`:''} ${location.origin}${call.path}`;
    button.disabled=call.method!=='GET';
    output.textContent=response?JSON.stringify(response,null,2):call.method==='GET'?'点击“发送请求”读取所选运行。':call.method==='POST'?'此页仅展示请求格式，写入值使用引擎单位；写入要求运行尚未结束，已完成的运行需先新建持续运行。':'此页仅展示订阅格式；已结束运行返回结束消息。';
  } catch(error) { path.textContent='';request.textContent='';output.textContent=error.message;button.disabled=true; }
}
async function apiSend() {
  const context=apiContext,kind=ui.apiKind||'read',call=apiCall(kind);
  if(call.method!=='GET')return;
  const response=await fetch(call.path,{headers:engine.authHeaders()}),body=await response.json();
  if(apiContextCurrent(context)&&(ui.apiKind||'read')===kind&&apiCall(kind).path===call.path)apiPreview(kind,{status:response.status,body});
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
  const meter=project().measurements?.find(m=>'measurement.'+m.id===id);
  if(meter){
    const key='measurement.'+meter.id;
    if(!state.charts.extra.some(c=>c.projectId===project().id&&c.canonicalKey===key))state.charts.extra.push({id:key,projectId:project().id,label:meter.label,unit:meter.unit.display_unit,canonicalKey:key,canonicalScale:meter.unit.display_scale,canonicalOffset:meter.unit.display_offset,identifier:key,sampleKey:key});
    state.charts.source='live';markDirty(project());navigate('curves');return;
  }
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
function chartSvg(...args){return runResultsView().chartSvg(...args);}
function resizeCharts() {
  for (const svg of root.querySelectorAll('svg[data-chart]')) {
    const data = chartRegistry.get(svg.id); if (!data) continue;
    const html = chartSvg(data.rows, data.keys, svg.id, svg.id === 'main-flow-chart' && state.charts.compare, data.options);
    FluidNetSvgDom.update(svg,html);
  }
}
function extraChartsMarkup(...args){return runResultsView().extraChartsMarkup(...args);}
function chartBindingsForRun(run=currentChartRun()) {
  if(state.charts.source==='live')return state.charts.extra.filter(v=>v.projectId===project().id);
  if(Array.isArray(run.chartBindings))return run.chartBindings;
  // Legacy records did not capture chart bindings. Ordinary variable bindings
  // remain useful; a current coupling could refer to entirely different equipment.
  return state.charts.extra.filter(v=>v.projectId===run.projectId&&!isCouplingChart(v));
}
function updateExtraCharts() { const e = document.getElementById('extra-charts'); if (e) FluidNetSvgDom.patch(e,extraChartsMarkup()); }
function downloadFile(name, text, type = 'application/json') {
  const blob = text instanceof Blob ? text : new Blob([text], { type: type + ';charset=utf-8' }), url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 3000); msg('已生成导出文件。');
}
// Match the workspace data limit in model_types/http.py; sizes are UTF-8 bytes.
const PROTOTYPE_JSON_MAX_BYTES = 64 * 1024 * 1024;
function exportData(format, id) {
  const csvCell = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  if (format === 'csv') {
    const run=currentChartRun(),h=run.history; if (!h.length) throw Error('当前数据来源没有曲线可导出。');
    const columns=Object.entries(overviewSeries(run)).map(([key,binding])=>({
      label:`${binding.key} [${binding.unit}]`,value:row=>row[key]}));
    columns.push(...chartBindingsForRun(run).map(binding=>({label:`${binding.canonicalKey || binding.identifier || binding.id} [${binding.unit}]`,
      value:row=>extraVariableValue(row,binding,state.charts.source==='live')})));
    downloadFile('fluidnet-curves.csv', '\uFEFF' + [['time_s',...columns.map(column=>column.label)],
      ...h.map(row=>[row.t,...columns.map(column=>column.value(row))])].map(row=>row.map(csvCell).join(',')).join('\r\n'), 'text/csv'); return;
  }
  let data, name;
  if (format === 'record' || format === 'report') { data = state.records.find(r => r.id === (id || ui.selectedRecord)) || state.records[0]; if (!data) throw Error('没有可导出的记录。'); name = data.id; }
  else if (format === 'models') { data = { format: 'fluidnet-prototype-models', schema: 1, moduleGroups: state.moduleGroups, modules: state.modules, models: state.models }; name = 'fluidnet-models'; }
  else if (format === 'variables') { data = { project: project().id, variables: projectVariables() }; name = 'fluidnet-variables'; }
  else if (format === 'messages') { data = state.messages; name = 'fluidnet-messages'; }
  else { data = clone(state); data.format = 'fluidnet-studio-prototype'; name = 'fluidnet-prototype'; }
  let json = JSON.stringify(data, null, 2);
  if (['fluidnet-studio-prototype','fluidnet-prototype-models'].includes(data?.format)
      && new Blob([json]).size > PROTOTYPE_JSON_MAX_BYTES) {
    const compact = JSON.stringify(data);
    if (new Blob([compact]).size <= PROTOTYPE_JSON_MAX_BYTES) json = compact;
  }
  downloadFile(name + '.json', json);
}
function validateImport(data) {
  const safeId = id => typeof id === 'string' && /^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id);
  if (!data || data.schema !== 1 || !Array.isArray(data.modules) || !data.modules.length || !Array.isArray(data.models)) throw Error('不是本版本的原型交换文件。');
  validateModuleGroups(data);
  if (data.modules.length > 256 || data.models.length > 500) throw Error('导入数据超出工作区容量。');
  backfillBuiltinParams(data);
  const unique = values => new Set(values).size === values.length;
  if (!unique(data.modules.map(m => m.id)) || !unique(data.models.map(m => m.id))) throw Error('模块或型号标识重复。');
  for (const m of data.modules) {
    // Validation reads each imported module's fields; normalizeState installs them only after import.
    // Contract-derived display names may contain '-' and exceed the old editor's
    // 48-character Python-name limit (e.g. D-24_in0 in a canvas composite).
    // Keep canonical IDs intact; these display names are never executed as Python.
    const displayName = value => typeof value === 'string' && (m.manifest
      ? /^[A-Za-z_][A-Za-z0-9_-]*$/.test(value) : isIdentifier(value));
    if (!safeId(m.id) || (!PARAM_DEFS[m.kind] && !m.manifest) || !displayName(m.code) || typeof m.name !== 'string' || !Array.isArray(m.ports) || !Array.isArray(m.variables) || !Array.isArray(m.channels) || !m.values || m.banks?.length !== 3 || m.bankNames?.length !== 3 || !m.source || typeof m.source.runtime !== 'string' || typeof m.source.header !== 'string' || m.source.design?.length !== 3 || m.source.design.some(code => typeof code !== 'string') || (m.designSource !== undefined && typeof m.designSource !== 'string') || !m.drawing) throw Error('模块定义不完整。');
    if (m.ports.length > 24 || m.variables.length > 160 || !unique(m.ports.map(p => p.id)) || !unique(m.variables.map(v => v.id))) throw Error('端口 / 变量标识重复或数量超限。');
    if (m.ports.some(p => !safeId(p.id) || !displayName(p.name) || !DOMAINS[p.domain] || !['in', 'out'].includes(p.direction) || !Number.isFinite(p.x) || !Number.isFinite(p.y))) throw Error('端口定义不合法。');
    if (m.variables.some(v => !displayName(v.name) || !['int', 'double', 'int[8]', 'double[8]'].includes(v.type) || v.port && !m.ports.some(p => p.id === v.port))) throw Error('变量定义不合法。');
    if (!m.variables.some(v => v.id === 'system:form') || !m.variables.some(v => v.id === 'system:mix')) throw Error('模块缺少工质字段。');
    if (!Number.isInteger(m.precision) || m.precision < 0 || m.precision > 8) throw Error('显示精度不合法。');
    numeric(m.drawing.width, 15, 60); numeric(m.drawing.height, 15, 55);
    for (const bank of [m.values, ...m.banks]) validateBank(m, bank);
  }
  for (const item of data.models) {
    const m = data.modules.find(m => m.id === item.moduleId);
    if (!safeId(item.id) || !m || typeof item.name !== 'string' || !Array.isArray(item.versions) || !item.versions.length) throw Error('型号引用或版本数据不完整。');
    readParams(item.params, m.kind,'',moduleParamDefs(m)); validateModelVariables(item, m);
  }
  if (data.format === 'fluidnet-prototype-models') return;
  if (!Array.isArray(data.projects) || !data.projects.length || data.projects.length > 20 || !unique(data.projects.map(p => p.id)) || !data.bench || !data.charts || !Array.isArray(data.records) || !Array.isArray(data.messages) || !Array.isArray(data.connectors) || !Number.isInteger(data.serial)) throw Error('项目、测试或运行数据不完整。');
  for (const p of data.projects) {
    controls.normalize(p);
    if (!safeId(p.id) || typeof p.name !== 'string' || !p.solver || !Array.isArray(p.pages) || !p.pages.length || p.pages.length > 8 || !p.run?.values || !Array.isArray(p.run.history) || !Array.isArray(p.run.events) || typeof p.control !== 'string') throw Error('项目结构不合法。');
    const ids = p.pages.flatMap(pg => pg.nodes?.map(n => n.id) || []); if (!unique(ids)) throw Error('项目设备标识重复。');
    for (const pg of p.pages) {
      if (!safeId(pg.id) || !Array.isArray(pg.nodes) || pg.nodes.length > 64 || !Array.isArray(pg.edges)) throw Error('画布结构不合法。');
      for (const n of pg.nodes) { const m = p.moduleSnapshots?.[n.moduleId] || data.modules.find(m => m.id === n.moduleId); if (!safeId(n.id) || !m || !Number.isFinite(n.x) || !Number.isFinite(n.y)) throw Error('设备引用不合法。'); readParams(n.params, m.kind, '', moduleParamDefs(m)); readParams(n.draft, m.kind, '', moduleParamDefs(m)); validateInstanceVariableState(n, m); }
      for (const e of pg.edges) if (!Array.isArray(e) || e.length !== 5 || !safeId(e[0])) throw Error('连接格式不合法。');
    }
    if(!unique(p.pages.map(pg=>pg.id)))throw Error('画布标识重复。');
    const connectionErrors=links.validate(p,n=>p.moduleSnapshots?.[n.moduleId]||data.modules.find(m=>m.id===n.moduleId),false);
    if(connectionErrors.length)throw Error(connectionErrors.map(error=>error.text).join('；'));
    numeric(p.solver.dt, .01, 60); numeric(p.solver.duration, 1, 86400);
  }
  if (!data.projects.some(p => p.id === data.activeProject) || !data.modules.some(m => m.id === data.bench.moduleId) || !data.bench.run?.values || !Array.isArray(data.bench.run.history) || !Array.isArray(data.bench.run.events)) throw Error('当前项目或测试引用无效。');
}
function showImportPreview(current, text, error = false) {
  if (modal !== current) return;
  const preview = document.getElementById('import-preview'), form = preview?.closest('form');
  if (!form) return;
  preview.textContent = text; preview.className = 'notice' + (error ? ' error' : '');
  const chooser = form.querySelector('input[name="file"]');
  if (error) chooser.setAttribute('aria-invalid', 'true'); else chooser.removeAttribute('aria-invalid');
  form.querySelector('button[type="submit"]').disabled = !!current.importReading || !current.importData;
}
function readImportFile(el) {
  const current = modal, file = el.files[0] || null, sequence = (current.importSequence || 0) + 1;
  Object.assign(current, { importSequence: sequence, importData: null, importFile: file, importReading: false });
  document.getElementById('dialog-error').hidden = true;
  if (!file) { showImportPreview(current, '请选择文件。导入前可以取消。'); return; }
  if (file.size > PROTOTYPE_JSON_MAX_BYTES) { showImportPreview(current, '检查失败：请使用不超过 64 MB 的原型 JSON。', true); return; }
  current.importReading = true;
  showImportPreview(current, '正在读取并检查文件…');
  const isCurrent = () => modal === current && current.importSequence === sequence && el.files[0] === file;
  Promise.resolve().then(() => file.text()).then(text => {
    if (!isCurrent()) return;
    const data = JSON.parse(text); validateImport(data);
    current.importData = data; current.importReading = false;
    showImportPreview(current, `${data.projects?.length || 0} 个项目 · ${data.modules.length} 个模块 · ${data.models.length} 个型号。确认后${data.format === 'fluidnet-prototype-models' ? '合并型号库' : '替换当前原型草稿'}。`);
  }).catch(error => {
    if (!isCurrent()) return;
    current.importData = null; current.importReading = false;
    showImportPreview(current, '检查失败：' + error.message, true);
  });
}
function importDialog() {
  openDialog('导入原型或型号库', '读取本设计版本的 JSON，先检查完整性，再显式应用。', '<div class="file-drop"><input type="file" name="file" accept=".json,application/json" aria-label="选择原型 JSON" required></div><div id="import-preview" class="notice" style="margin-top:16px">请选择文件。导入前可以取消。</div>', () => {
    const incoming = modal.importData, file = document.querySelector('#dialog-form input[name="file"]').files[0];
    if (!incoming || modal.importReading || !file || file !== modal.importFile) throw Error('请先选择并读取有效文件。');
    validateImport(incoming);
    if (incoming.format === 'fluidnet-prototype-models') {
      const conflicts = incoming.models.filter(m => state.models.some(v => v.id === m.id));
      if (conflicts.length) throw Error(`已有 ${conflicts.length} 个相同标识的型号。为避免覆盖，请使用完整原型恢复或导入不同型号。`);
      const mergedGroups = collectModuleGroups({ modules: [...state.modules, ...incoming.modules], moduleGroups: [...state.moduleGroups, ...(incoming.moduleGroups || [])] });
      state.moduleGroups = mergedGroups;
      state.modules.push(...clone(incoming.modules.filter(m => !state.modules.some(v => v.id === m.id)))); state.models.push(...clone(incoming.models));
    } else {
      replaceWorkspaceState({...incoming,workspaceRevision:state.workspaceRevision},()=>backupLocalDraft(STORAGE_KEY+'-before-import')); state.projects.forEach(p => { if (p.run.status === 'running') p.run.status = 'paused'; }); if (state.bench.run.status === 'running') state.bench.run.status = 'paused';
    }
    ui.floats = []; undoStack = []; redoStack = []; ui.selectedNode = ''; normalizeState(); markDirty(); navigate('home'); msg('导入已应用；点击保存原型以保留。');
  }, '应用导入');
  const current = modal, chooser = document.querySelector('#dialog-form input[name="file"]');
  readImportFile(chooser);
  chooser.addEventListener('cancel', () => {
    if (modal !== current) return;
    chooser.value = ''; readImportFile(chooser);
  });
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
  if(featureActions().dispatch(action,el))return;
  const d = el.dataset, id = d.id;
  const changes = { 'project-filter': 'projectFilter', 'project-view': 'projectView', 'module-category': 'category', 'module-view': 'moduleView', 'model-filter': 'modelFilter', 'bench-tab': 'benchTab', 'run-filter': 'runFilter', 'settings-tab': 'settingsTab', 'connection-tab': 'connectionTab', 'node-domain': 'nodeDomain' };
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
    case 'export-old-draft': {const original=localStorage.getItem(STORAGE_KEY+'-before-workspace');if(!original)throw Error('没有载入前的浏览器草稿备份。');downloadFile('fluidnet-browser-draft.json',JSON.stringify(FluidNetDraftStore.parse(original)));break;}
    case 'restore-workspace-revision': {const revision=Number(d.revision);confirmChange('恢复工作区修订 '+revision,'当前草稿先备份到浏览器；恢复后生成一个新修订，已有运行档案保留。',()=>engine.restoreRevision(revision).then(receipt=>msg('已恢复为修订 '+receipt.revision)).catch(error=>msg(error.message,true)));break;}

    case 'reload-workspace':
      if(workspaceStorage().isSaving())throw Error('请等待当前保存结束。');
      confirmChange('载入服务器工作区','当前草稿将先备份到浏览器；可先导出原型保留独立文件。',()=>engine.init(true));break;
    case 'refresh-archives': engine.refreshArchives();break;
    case 'delete-archive': confirmChange('删除运行档案','将删除该运行的服务端快照和历史。',()=>engine.deleteArchive(id).then(()=>{state.records=state.records.filter(r=>r.id!==id);render();}).catch(error=>msg(error.message,true)));break;
    case 'open-archive': engine.openArchive(id).catch(error=>msg(error.message,true));break;
    case 'resume-archive': resumeArchiveDialog(id).catch(error=>msg(error.message,true));break;
    case 'theme': ui.theme = ui.theme === 'dark' ? 'light' : 'dark'; saveUI(); render(); break;
    case 'open-project': closeDialog(); if (id) openProject(id); break;
    case 'start-modeling': startModeling(); break;
    case 'toggle-chart': ui.showChart = !ui.showChart; ui.pinnedChart = null; saveUI(); refreshWorkbench(); break;
    case 'full-curves': state.charts.source = 'live'; ui.pinnedChart = null; navigate('curves'); break;
    case 'release-cursor': ui.pinnedChart = null; ui.chartCursor = null; refreshWorkbenchChart(); break;
    case 'guided-demo': state.selectedModule = 'valve'; ui.bank = 1; openEditor('valve', 'channels'); msg('从端口与通路开始，再编辑库值、保存型号并应用到项目。'); break;
    case 'new-project':
      openDialog('新建项目', '选择一份示例作为起点，或创建空白画布。', `<div class="stack">${field('name', '项目名称', '新管网项目', 'required maxlength="50"')}${selectField('template', '起始内容', [['blank', '空白画布'], ['cold-storage-blank', '空白冷库画布 · 自选设备组装'], ['water', '泵阀并联管网'], ['heat', '双侧换热机组'], ['tank', '水箱液位调节']], 'blank')}</div>`, data => {
        if (state.projects.length >= 20) throw Error('当前原型最多保存 20 个项目。');
        const name = data.name.trim(); if (!name) throw Error('请输入项目名称。');
        const pg = data.template === 'water' ? waterPage() : data.template === 'heat' ? heatPage() : data.template === 'tank' ? tankPage() : { id: 'main', name: '主系统', nodes: [], edges: [], zoom: 1, pan: [0, 0] };
        const p = makeProject(uid('project'), name, '', pg);
        if (['blank','cold-storage-blank','heat'].includes(data.template))p.controlPrograms=[];
        if(data.template==='cold-storage-blank') {
          Object.assign(p,{modelingDomain:'refrigeration',medium:'r134a',fluid:'HEOS::R134a',fluidReference:'mass',fluidConfig:{fluid:'HEOS::R134a',phase_policy:'any'}});
          Object.assign(p.solver,{mode:'dynamic',dt:1,duration:60,executionMode:'fast'});ui.showLibrary=true;
        }
        projectState.addProject(state,p); normalizeState(); markDirty(p); openProject(p.id);
      }, '创建项目'); break;
    case 'duplicate-project': {
      if(state.projects.length>=20)throw Error('最多保存 20 个项目。');
      const original=state.projects.find(p=>p.id===id);if(!original)break;
      const p=clone(original);p.id=uid('project');p.name+=' 副本';p.run=emptyRun();p.modified='本地草稿';
      const copiedCharts=clone(state.charts.extra.filter(binding=>binding.projectId===original.id));
      for(const binding of copiedCharts){binding.id=uid('chart');binding.projectId=p.id;}
      projectState.addProject(state,p);state.charts.extra.push(...copiedCharts);markDirty(p);persistLocal();render();break;
    }
    case 'new-canvas':
    case 'rename-canvas': {
      const pg = action === 'rename-canvas' && project().pages.find(pg => pg.id === id);
      openDialog(pg ? '重命名画布' : '新增画布', project().name, field('name', '画布名称', pg?.name || `画布 ${project().pages.length + 1}`, 'required maxlength="40"'), data => {
        const name = data.name.trim(); if (!name) throw Error('请输入画布名称。'); if (!pg && project().pages.length >= 8) throw Error('当前原型每个项目最多演示 8 张画布。');
        remember(); if (pg) pg.name = name; else { const next = { id: uid('canvas'), name, nodes: [], edges: [], zoom: 1, pan: [0, 0] }; projectState.addCanvas(project(),next); }
        ui.selectedNode = ''; ui.connecting = null; markDirty(project()); render();
      }, pg ? '保存名称' : '新增画布'); break;
    }
    case 'page-links': pageLinksDialog(); break;
    case 'add-page-link': pageLinkDialog(d.node, d.port); break;
    case 'connect-device-port': pageLinkDialog(d.node, d.port, null, true); break;
    case 'edit-page-link': pageLinkDialog(null, null, id); break;
    case 'jump-page-link': jumpPageLink(id, d.node); break;
    case 'move-device-page': moveDevicePage(id); break;
    case 'new-module-group': moduleGroupDialog(); break;
    case 'rename-module-group': moduleGroupDialog(d.value); break;
    case 'delete-module-group': removeModuleGroup(d.value); break;
    case 'move-module-group': moveModuleGroup(id); break;
    case 'performance-library': openPerformanceLibrary(id||undefined); break;
    case 'equipment-library': openEquipmentLibrary(); break;
    case 'new-module':
      openDialog('新建算法模块', '从模板开始，编辑设备的端口、参数和算法；保存版本后即可放入项目。', `<div class="fields">${field('name', '模块名称', '自定义调节阀', 'required maxlength="40"')}${field('code', '模块标识', 'CUSTOM_VALVE', 'required pattern="[A-Za-z_][A-Za-z0-9_]*" maxlength="48"')}${selectField('base', 'Python 模板', [['template:resistance','两端口局部阻力'],['template:custom_pressure_drop','自定义压降公式'],['template:pump','泵／风机'],['template:heat_exchanger','双侧换热'],['template:managed_state','受管理状态'],['template:refrigeration_throttle','制冷等焓节流阀'],['template:refrigeration_compressor','制冷压缩机本构'],['template:refrigeration_condenser','制冷冷凝器本构'],...state.modules.filter(m=>m.runtime==='python').map(m=>[m.id,m.name])], 'template:resistance')}${selectField('category', '所属分组', moduleGroupNames().map(name => [name, name]), ui.route === 'modules' && ui.category !== '全部模块' ? ui.category : '自定义模块')}</div>`, async data => {
        if (!isIdentifier(data.code) || state.modules.some(m => m.code === data.code)) throw Error('模块标识需合法且唯一。');
        if (state.modules.length >= 256) throw Error('已达到工作区模块数量上限（256）。');
        if (!moduleGroupNames().includes(data.category)) throw Error('请选择已有分组。');
        if (!data.name.trim()) throw Error('请输入模块名称。');
        if (!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(data.code) || state.modules.some(m=>m.id===data.code.toLowerCase())) throw Error('模块标识需以字母开头且唯一。');
        const workspace=state,dialog=modal;
        const m=data.base.startsWith('template:') ? await engine.newTemplate(data.code.toLowerCase(),data.name.trim(),data.category,data.base.slice(9)) : engine.newModule(data.code.toLowerCase(),data.name.trim(),data.category,data.base);
        if(state!==workspace||modal!==dialog)return;
        if(state.modules.some(item=>item.id===m.id||item.code===data.code))throw Error('模块标识已存在，请更换。');
        state.modules.push(m);markDirty(m);openEditor(m.id,'drawing');
      }, '创建模块'); break;
    case 'edit-contract-item': editContractItem(d.section,id); break;
    case 'edit-module-metadata': editModuleMetadata(); break;
    case 'edit-module-parameter': editModuleParameter(id); break;
    case 'edit-pump-curve': editPumpCurve(id,d.instanceParam,el.dataset.configReadonly==='true'); break;
    case 'create-composite': {
      const choices=activePage().nodes.filter(n=>moduleOf(n).manifest?.solver_model!=='pressure_source' && moduleOf(n).kind!=='source');
      openDialog('封装设备组','选择设备，生成带精确子版本绑定的组合草稿。',`<div class="fields">${field('id','组合标识','custom_group','required pattern="[A-Za-z][A-Za-z0-9_]*"')}${field('name','组合名称','设备组','required')}</div><div class="stack">${choices.map(n=>`<label class="check-label"><input name="node_${n.id}" type="checkbox" ${ui.selectedNode===n.id?'checked':''}>${esc(n.id+' · '+n.name)}</label>`).join('')}</div>`,async data=>{
        const ids=choices.filter(n=>data['node_'+n.id]).map(n=>n.id);
        if(!ids.length)throw Error('请选择至少一个设备。');
        if(state.modules.some(m=>m.id===data.id))throw Error('组合标识已存在。');
        const workspace=state,owner=project(),dialog=modal;
        const m=await engine.newComposite(owner,ids,data.id,data.name);
        if(state!==workspace||modal!==dialog||project()!==owner)return;
        if(state.modules.some(item=>item.id===m.id))throw Error('组合标识已存在，请更换。');
        state.modules.push(m);markDirty(m);openEditor(m.id,'contract');
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
    case 'inspect-module-replay': moduleReplay.load(mod().authoringReplay,mod().authoringDiagnostics); break;
    case 'bench-failure-replay': moduleReplay.load(state.bench.run.failureReplay,state.bench.run.diagnostics); break;
    case 'archive-module-replay': moduleReplay.archive(id); break;
    case 'run-module-replay': moduleReplay.run(); break;
    case 'download-module-replay': moduleReplay.exportInput(); break;
    case 'close-module-replay': moduleReplay.close(); break;
    case 'export-module-replay': downloadFile(`${mod().id}-replay.json`,JSON.stringify(mod().authoringReplay,null,2)); break;
    case 'configure-module-tests': configureAuthoringSuite(mod()); break;
    case 'module-test-suite': runAuthoringSuite(mod()); break;
    case 'cancel-module-suite': ui.moduleSuiteAbort?.abort(); break;
    case 'validate-module-contract': engine.checkModule(mod(),true); break;
    case 'edit-module': openEditor(id || state.selectedModule, d.tab || 'drawing'); break;
    case 'module-doc': openModuleDoc(id); break;
    case 'insert-module': newInstance(id); navigate('workbench'); break;
    case 'use-module': useModuleDialog(id || state.selectedModule); break;
    case 'place-module': ui.placing = ui.placing === id ? null : id; ui.connecting = null; render(); break;
    case 'insert-defaults': remember(); {
      const w = waterPage(), used = project().pages.filter(pg => pg !== activePage()).flatMap(pg => pg.nodes.map(n => n.id));
      const mapping = Object.fromEntries(w.nodes.map(n => [n.id, used.includes(n.id) ? uid(n.id) : n.id]));
      w.nodes.forEach(n => n.id = mapping[n.id]); w.edges = w.edges.map(e => [uid('edge'), mapping[e[1]], e[2], mapping[e[3]], e[4]]);
      activePage().nodes = w.nodes; activePage().edges = w.edges;
    } markDirty(project()); render(); break;
    case 'device-overview': openDevice(id); setDeviceTab(ui.floats.find(f=>f.id===id),'overview'); renderFloats(); break;
    case 'open-device': openDevice(id); setDeviceTab(ui.floats.find(f=>f.id===id),'parameters'); renderFloats(); break;
    case 'apply-instance': applyInstanceDialog(instance(id)); break;
    case 'apply-instance-bank': applyInstanceBank(instance(id), Number(d.bank)); break;
    case 'capture-instance-bank': captureInstanceBank(instance(id), Number(d.bank)); break;
    case 'instance-array': editInstanceArray(instance(id), d.instanceValue, Number(d.instanceSource)); break;
    case 'copy-device': copyDevice(id); break;
    case 'rotate-device': rotateDevice(id, d.direction === '-1' ? -1 : 1); break;
    case 'device-variables': openDeviceVariables(id, d.variable); break;
    case 'choose-device-model': chooseDeviceModel(id); break;
    case 'device-definition': openDeviceDefinition(id, d.variable); break;
    case 'edit-device-library': editDeviceLibrary(id, d.variable); break;
    case 'return-device': returnToDevice(); break;
    case 'observe-instance-variable': observeInstanceVariable(id, d.variable); break;
    case 'project-group-tools': projectGroupTools(); break;
    case 'project-find': projectFind(); break;
    case 'project-find-node': {if(project().id!==d.project)throw Error('项目已变化');const found=links.locate(project(),id);if(!found)throw Error('设备不存在');closeDialog();project().activePage=found.page.id;fitNetwork(found.page);ui.selectedNode=id;render();openDevice(id);break;}
    case 'device-batch-edit': openDeviceBatch(); break;
    case 'configure-module-panel': configureDevicePanel(); break;
    case 'configure-device-panel': configureDevicePanel(id); break;
    case 'equipment-selection': openEquipmentSelection(id); break;
    case 'coil-geometry-design': openEquipmentSelection(id); equipmentSelection.geometry(id); break;
    case 'equipment-provenance': openEquipmentSelection(id); equipmentSelection.provenance(id); break;
    case 'save-instance-model': saveInstanceModel(id); break;
    case 'toggle-library': ui.showLibrary = !ui.showLibrary; saveUI(); refreshWorkbench(); break;
    case 'validate': systemInspection.check(); break;
    case 'locate-issue': closeDialog(); if (d.page) project().activePage = d.page; navigate('workbench'); if (id) openDevice(id); break;
    case 'draw-center': for (const p of mod().ports) { p.x = p.direction === 'in' ? 20 : 80; p.y = 30 + mod().ports.filter(x => x.direction === p.direction).indexOf(p) * 25; } markDirty(mod()); render(); break;
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
      if (state.projects.some(p => p.pages.some(pg => pg.edges.some(e => [1, 3].some(i => p.pages.flatMap(page=>page.nodes).find(n => n.id === e[i])?.moduleId === m.id && e[i + 1] === id))))) throw Error('项目中仍有连接使用此端口，请先断开连接。');
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
    case 'run-bench': commandRun('bench', d.command); break;
    case 'record-bench': recordRun('bench'); break;
    case 'run-project': commandRun('project', d.command); break;
    case 'stop-task': commandRun('project', 'stop', id); break;
    case 'record-project': recordRun('project'); break;
    case 'tasks': ui.taskDrawer = !ui.taskDrawer; renderFloats(); break;
    case 'inspect-run': systemInspection.run(id); break;
    case 'archive-report': engine.exportRunReport(id,d.format).then(blob=>downloadFile('run-'+id+'.'+d.format,blob)).catch(error=>msg(error.message,true)); break;
    case 'add-chart-variable': chooseChartVariables(); break;
    case 'choose-control-vars': chooseChartVariables(true); break;
    case 'add-specific-curve': addChartVariable(id, d.label); break;
    case 'device-curve': {
      const v = projectVariables().find(v => v.nodeId === id && v.origin === 'port' && v.variableId.endsWith(':FLOW'));
      if (!v) throw Error('此设备暂未提供出口流量采样。');
      addChartVariable(v.id); break;
    }
    case 'add-control-program': {
      const p=project(),programs=controls.normalize(p);let suffix=1;
      while(programs.some(program=>program.id==='control_'+suffix))suffix++;
      openDialog('新建控制脚本','脚本各自保存输入输出、采样周期和状态。',field('id','脚本标识','control_'+suffix,'required maxlength="81"')+field('name','脚本名称','控制程序 '+suffix,'required maxlength="80"'),data=>{
        controls.add(p,data.id.trim(),data.name.trim());ui.controlOutput='控制脚本尚未预览。';markDirty(p);render();
      },'新建');break;
    }
    case 'remove-control-program': {const p=project(),id=d.id;confirmChange('删除控制脚本',`删除 ${id}；当前运行仍使用启动时的脚本快照。`,()=>{controls.remove(p,id);ui.controlOutput='控制脚本尚未预览。';markDirty(p);render();});break;}
    case 'control-template': {
      const interlock=d.kind==='interlock';
      confirmChange(interlock?'载入机房联锁控制模板':'载入 Python 控制示例',
        interlock?'替换所选脚本、输入和输出声明，启用状态保持关闭；模板要求存在两台循环泵、止回阀和供回水总管的 Discharge／Suction 节点。'
          :'替换所选脚本、输入和输出声明，启用状态保持关闭；示例要求存在 V1 阀门。',
        ()=>{const p=project();controls.update(p,interlock
          ?{source:controlTemplate('interlock'),language:'python',enabled:false,
            inputs:['Discharge.common.pressure_pa','Suction.common.pressure_pa'],
            outputs:['Pump1.param.running','Pump2.param.running']}
          :{source:controlTemplate(),language:'python',enabled:false,inputs:['V1.mass_flow_kg_s'],outputs:['V1.param.opening_ratio']});
          markDirty(p);render();});break;
    }
    case 'preview-control': {
      const owner=project(),scriptId=owner.selectedControlId;
      ui.controlOutput='正在执行一个控制周期…';document.getElementById('control-output').textContent=ui.controlOutput;
      engine.previewControl(owner).then(result=>{if(project()!==owner||owner.selectedControlId!==scriptId)return;ui.controlOutput='预览成功（未应用到项目）\n'+JSON.stringify(result,null,2);const el=document.getElementById('control-output');if(el)el.textContent=ui.controlOutput;}).catch(error=>{if(project()!==owner||owner.selectedControlId!==scriptId)return;ui.controlOutput='预览失败：'+error.message;const el=document.getElementById('control-output');if(el)el.textContent=ui.controlOutput;msg(error.message,true);});break;
    }

    case 'api-example': ui.apiKind = d.value; apiPreview(d.value); root.querySelectorAll('[data-action="api-example"]').forEach(e => e.classList.toggle('active', e.dataset.value === d.value)); break;
    case 'api-refresh': apiContext=null; apiPreview(); break;
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
  projectState.setDraft(ownerOfInstance(n),n,{[d.instanceParam]:value});
  el.closest('.parameter-row')?.classList.toggle('edited', !sameValue(value, n.params[d.instanceParam]));
  const float = el.closest('.floater'), pending = float?.querySelector('[data-pending-for]');
  if (pending) { pending.textContent = `${pendingCount(n)} 项待应用`; pending.className = `badge ${pendingCount(n) ? 'warn' : 'good'}`; }
  const apply = float?.querySelector('[data-action="apply-instance"]'); if (apply) apply.disabled = !pendingCount(n);
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
  if ('apiWrite' in d) { apiContext.writeValues ||= {}; apiContext.writeValues[apiContext.selected[ui.apiKind||'read']]=value; return; }
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
    return;
  }
  if (d.instanceName) { const n = instance(d.instanceName); if (value.trim()) projectState.updateNode(ownerOfInstance(n),n,{name:value}); markDirty(project()); return; }
  if (d.valueId) {
    const v = mod().variables.find(v => v.id === d.valueId); if (Number(d.bank) < 0 || !v.writable) return;
    mod().banks[Number(d.bank)][d.valueId] = value === '' ? '' : Number(value); el.closest('td')?.classList.add('edited'); markDirty(mod()); return;
  }
  if ('bankName' in d) { mod().bankNames[Number(d.bankName)] = value; markDirty(mod()); return; }
  if (d.projectField && ['name', 'description'].includes(d.projectField)) { if (d.projectField !== 'name' || value.trim()) project()[d.projectField] = value; markDirty(project()); }
}
function handleChange(el) {
  if(canvasView().change(el))return;
  const d = el.dataset, value = el.value, p=project(); let redraw = true;
  el.removeAttribute('aria-invalid');
  const physicalSetting=d.solverField||d.solverOption||d.circuitField||'solverContinuous' in d
    ||'liveMode' in d||'liveSpeed' in d||'projectPhasePolicy' in d||['medium','fluid','fluidReference'].includes(d.projectField);
  if(physicalSetting)assertProjectSettingsEditable(p);
  const dynamicSetting='solverContinuous' in d||'liveMode' in d||'liveSpeed' in d||['duration','dt'].includes(d.solverField);
  if(dynamicSetting&&p.solver.mode==='steady')throw Error('此设置仅用于动态运行；请先切换运行模式。');
  if('liveSpeed' in d&&p.solver.executionMode==='fast')throw Error('速度倍率仅用于按真实时间运行。');
  if(d.solverField==='duration'&&p.solver.continuous)throw Error('请先取消持续运行，再设置仿真时长。');
  if ('apiVariable' in el.dataset) { apiContext.selected[ui.apiKind||'read']=el.value; apiPreview(); return; }
  if ('apiWrite' in el.dataset) { apiPreview(); return; }
  if (d.deviceModelSource) { document.getElementById('device-model-preview').innerHTML = instanceModelPreview(instance(d.deviceModelSource), value); return; }
  if ('workbenchChart' in d) { ui.workbenchChart = value; ui.pinnedChart = null; saveUI(); retainFocus(); return; }
  if (el.type === 'file' && modal && el.name === 'file') {
    readImportFile(el); return;
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
  else if ('modulePrecision' in d) {
    const precision = value === '' ? null : Number(value);
    if (![null,2,4,6,8].includes(precision)) throw Error('请选择按模块定义或 2、4、6、8 位小数。');
    ui.modulePrecision = precision; saveUI();
  }
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
    const n = instance(d.instanceModel); if (value) stageModel(n, value); else { projectState.updateNode(ownerOfInstance(n),n,{draftModelId:null,draftModelVersion:null}); markDirty(project()); }
  }
  else if (d.instanceSwitch) { const n = instance(d.id), f = paramDefs(n).find(f => f[0] === d.instanceSwitch); projectState.setDraft(ownerOfInstance(n),n,{[f[0]]:el.checked ? f[4] : f[3]}); markDirty(project()); }
  else if (d.instanceParam) { setInstanceParamDraft(el); redraw = false; }  // a blur-driven change must not replace the float DOM mid-click
  else if ('benchModule' in d) { setBench(value); return; }
  else if (d.benchParam) { setBenchParam(el); }
  else if ('benchFluid' in d) { if (['running','solving'].includes(state.bench.run.status)) throw Error('停止测试后编辑工质。'); state.bench.boundary.fluid=value.trim(); markDirty(); }
  else if (d.benchBoundary) { if (state.bench.run.status === 'running') throw Error('暂停后编辑测试边界。'); state.bench.boundary[d.benchBoundary] = numeric(value, d.benchBoundary === 'temperature' ? -273 : .001, 100000); markDirty(); }
  else if ('benchStep' in d) { state.bench.run.step = numeric(value, .01, 10); markDirty(); }
  else if ('chartSource' in d) { ui.pinnedChart = null; state.charts.source = value; markDirty(); }
  else if ('chartCompare' in d) { state.charts.compare = el.checked; markDirty(); }
  else if ('chartRange' in d) { state.charts.range = value; markDirty(); if (value === 'all') engine.loadOverview(project()); }
  else if ('solverContinuous' in d) { project().solver.continuous = el.checked; markDirty(project()); }
  else if ('liveMode' in d) {
    if(!['realtime','fast'].includes(value))throw Error('请选择按真实时间运行或快速计算。');
    p.solver.executionMode=value;markDirty(p);
  }
  else if ('liveSpeed' in d) { p.solver.speedRatio=numeric(value,.1,100);markDirty(p);redraw=false; }
  else if ('projectPhasePolicy' in d) {
    if(!['single_phase','liquid','gas','any'].includes(value))throw Error('请选择有效的相态策略。');
    p.fluidConfig={...p.fluidConfig,phase_policy:value};markDirty(p);redraw=false;
  }
  else if (d.projectField) {
    if(d.projectField==='name'&&!value.trim())throw Error('项目名称不能为空；已保留原名称。');
    if(d.projectField==='name'&&value.trim().length>50)throw Error('项目名称最多 50 个字符。');
    if(d.projectField==='medium'&&!MEDIA.some(([key])=>key===value))throw Error('请选择有效的预设介质。');
    if(d.projectField==='fluidReference'&&!['mass','mole'].includes(value))throw Error('请选择质量分数或摩尔分数。');
    p[d.projectField]=['name','fluid'].includes(d.projectField)?value.trim():value;
    el.value=p[d.projectField];markDirty(p);redraw=false;
  }
  else if(d.circuitField){
    const row=p.circuitFluids?.[Number(d.index)];if(!row)throw Error('回路工质配置已不存在。');
    if(d.circuitField==='anchor'){
      if(!anchorOptions(p).some(([key])=>key===value))throw Error('请选择仍存在的流体或制冷剂端口。');
      const [instance_id,port_id]=value.split(':');row.anchor={instance_id,port_id};
    }else{
      if(d.circuitField==='medium'&&!MEDIA.some(([key])=>key===value))throw Error('请选择有效的预设介质。');
      if(d.circuitField==='fluidReference'&&!['mass','mole'].includes(value))throw Error('请选择质量分数或摩尔分数。');
      row[d.circuitField]=value.trim();el.value=row[d.circuitField];
    }
    markDirty(p);redraw=false;
  }
  else if (d.solverOption) {
    if(d.solverOption==='property_coupling'){
      if(!['reference','node'].includes(value))throw Error('请选择有效的物性反馈方式。');
      if(p.solverOptions?.moist_air&&value!=='node')throw Error('湿空气计算必须使用温度与密度联算。');
    }
    p.solverOptions ||= {};p.solverOptions[d.solverOption]=value;markDirty(p);
  }
  else if (d.solverField) {
    const bounds = { duration: [1, 86400], dt: [.01, 60], massAtol: [1e-12, 1], pressureAtol: [1e-12, 100000], maxIter: [5, 500] };
    const choices={mode:['dynamic','steady'],hydraulicMethod:['auto','dense','sparse']}[d.solverField];
    if(choices&&!choices.includes(value))throw Error('请选择有效的运行模式或水力算法。');
    p.solver[d.solverField]=choices?value:numeric(value,...bounds[d.solverField],d.solverField==='maxIter');
    markDirty(p);redraw=!!choices;
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
const svgPoint=(svg,event)=>FluidNetWorkspaceInteractions.svgPoint(svg,event);
let workspaceInput,featureRouter;
function workspaceInteractions(){return workspaceInput ||= FluidNetWorkspaceInteractions.create({
  root,document,getView:()=>({modal:!!modal,route:ui.route,drawing:ui.moduleTab==='drawing',placing:ui.placing,selectedNode:ui.selectedNode,selectedEdge:ui.selectedEdge}),
  canvas:{owner:project,page:activePage,node:instance,svg:()=>document.getElementById('network'),remember,
    move:(node,x,y)=>{projectState.updateNode(project(),node,{x,y});canvasView().move(node.id);},
    pan:value=>{activePage().pan=value;document.getElementById('network').setAttribute('viewBox',networkViewBox(activePage()));},
    flush:()=>canvasView().flush(),commit:()=>{markDirty(project());refreshWorkbench();},connect:connectPort,insert:newInstance,hasModule:id=>state.modules.some(m=>m.id===id),
    rotate:rotateDevice,undo,copy:copyDevice,paste:pasteDevice,removeNode:deleteNode,removeEdge:deleteEdge,
    pageSelect:id=>{if(!project().pages.some(p=>p.id===id))throw Error('画布已不存在');project().activePage=id;ui.selectedNode='';ui.selectedEdge='';render();},
    zoom:factor=>{activePage().zoom=clamp(activePage().zoom*factor,.35,3);refreshWorkbench();},fit:()=>{fitNetwork();refreshWorkbench();},grid:()=>{ui.pageGrid=!ui.pageGrid;saveUI();refreshWorkbench();}},
  selection:{ids:groupSelected,group:groupSelection,node:id=>{ui.selectedNode=id;},single:id=>{ui.selectedNode=id;ui.selectedEdge='';syncDeviceSelection();},edge:id=>{ui.selectedEdge=id;ui.selectedNode='';refreshWorkbench();},
    clearConnection:()=>{ui.connecting=null;},mode:mode=>{ui.canvasMode=mode;ui.placing=null;if(mode==='select'){ui.connecting=null;refreshWorkbench();}else msg('点击两个空闲端口建立连接，也可以拖动连线。');}},
  editor:{current:mod,svg:()=>document.getElementById('module-drawing'),select:id=>{ui.editorPort=id;},
    move:(id,x,y)=>{const p=mod().ports.find(p=>p.id===id);if(!p)throw Error('端口已不存在');p.x=x;p.y=y;document.getElementById('module-drawing').innerHTML=drawingSVG(mod());},
    commit:()=>{markDirty(mod());render();},nudge:event=>{const p=mod().ports.find(p=>p.id===ui.editorPort);if(!p)return;event.preventDefault();p.x=clamp(p.x+(event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0),5,95);p.y=clamp(p.y+(event.key==='ArrowDown'?1:event.key==='ArrowUp'?-1:0),10,85);markDirty(mod());render();}},
  windows:{beginPointer:event=>deviceWindows().beginPointer(event),movePointer:(ticket,x,y)=>deviceWindows().movePointer(ticket,x,y),finishPointer:ticket=>deviceWindows().finishPointer(ticket),open:openDevice},
  charts:{hover:chartHover,pin:event=>{ui.pinnedChart=ui.pinnedChart?null:event.target.closest('svg').id;chartHover(event,true);}},
  shell:{error:error=>msg(error.message,true),render,action:handleAction,clearContext:()=>{contextMenu=null;root.querySelector('.context-menu')?.remove();},dismissContext:()=>{if(contextMenu){contextMenu=null;renderFloats();}},
    context:(id,x,y)=>{contextMenu={id,x:clamp(x,70,innerWidth-202),y:clamp(y,60,innerHeight-370)};syncDeviceSelection();renderFloats();}}
});}
function featureActions(){
  if(featureRouter)return featureRouter;
  const router=FluidNetActionRouter.create(error=>msg(error.message,true));
  for(const [name,handler] of Object.entries(workspaceInteractions().actions))router.action(name,handler);
  for(const name of ['add-meter','edit-meter','remove-meter','meter-curve'])router.action(name,measurementAction);
  for(const name of deviceWindows().actionNames)router.action(name,(action,el)=>deviceWindows().action(action,el));
  for(const feature of [moduleEditorView(),runResultsView()])for(const name of feature.actionNames)router.action(name,(action,el)=>feature.action(action,el));
  for(const [prefix,feature] of [['canvas-',()=>canvasView()],['wf-',()=>workflows],['batch-',()=>scenarioBatches],['air-',()=>airSide],['cs-',()=>coldStorage]])router.prefix(prefix,(action,el)=>feature().action(action,el));
  for(const [name,handler] of Object.entries({
    'save-module-version':()=>engine.saveModule(mod()),'module-versions':()=>engine.versions(mod()),'load-module-version':(_,el)=>engine.loadVersion(mod(),Number(el.dataset.version)),
    'module-example':(_,el)=>createModuleExample(el.dataset.id),'test-module':(_,el)=>setBench(el.dataset.id)
  }))router.action(name,handler);
  return featureRouter=router;
}
function selectCodeTarget(kind) {
  if (!['runtime', 'header', 'design'].includes(kind)) return;
  ui.codeKind = kind;
  const picker = root.querySelector('[data-code-target]'); if (picker) picker.value = kind;
  saveUI();
}
root.addEventListener('click', e => { if(e.target.closest('[data-trace-close]')) { ui.canvasInspection=null;paintCanvasInspection(); } });
root.addEventListener('keydown', e => { if(e.key==='Escape') { ui.canvasInspection=null;paintCanvasInspection(); } });
root.addEventListener('pointerover', e => { if (!workspaceInput?.busy()) showCanvasInspection(e.target); });
root.addEventListener('pointerout', e => { if (!workspaceInput?.busy()) showCanvasInspection(e.relatedTarget); });
root.addEventListener('focusin', e => { if (e.target.closest('#network [data-node]')) showCanvasInspection(e.target); if (e.target.matches('textarea[data-code-kind]')) selectCodeTarget(e.target.dataset.codeKind); });
root.addEventListener('focusout', e => { if (e.target.closest('#network [data-node]')) showCanvasInspection(e.relatedTarget); });
root.addEventListener('scroll', e => { if (e.target.matches?.('textarea[data-code-kind]')) e.target.previousElementSibling.scrollTop = e.target.scrollTop; }, true);
root.addEventListener('input', e => { try { handleInput(e.target); } catch (err) { msg(err.message, true); } });
root.addEventListener('change', e => { try { handleChange(e.target); } catch (err) { restoreProjectSettingInput(e.target);e.target.setAttribute('aria-invalid', 'true'); msg(err.message, true); } });
root.addEventListener('submit', async e => {
  if (e.target.getAttribute('id') !== 'dialog-form') return; e.preventDefault();
  const current = modal; if (!current?.onSubmit || current.submitting) return;
  const form=e.target,data=Object.fromEntries(new FormData(form));
  const controls=[...form.querySelectorAll('input,select,textarea,button:not([data-action="close-dialog"])')].map(el=>[el,el.disabled]);
  const submit=form.querySelector('[type="submit"]'),label=submit.textContent;
  current.submitting=true;form.setAttribute('aria-busy','true');
  form.querySelector('#dialog-error').hidden=true;
  controls.forEach(([el])=>el.disabled=true);submit.textContent='处理中…';
  try { await current.onSubmit(data); if (modal === current) closeDialog(); }
  catch (err) { if(modal===current){const target=form.querySelector('#dialog-error');target.hidden=false;target.textContent=err.message;} }
  finally { current.submitting=false;if(modal===current){form.removeAttribute('aria-busy');controls.forEach(([el,disabled])=>el.disabled=disabled);submit.textContent=label;} }
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
  if (e.key === 'Escape') { workspaceInput?.cancel(); closeDialog(); contextMenu = null; ui.connecting = null; ui.placing = null; ui.pinnedChart = null; if(ui.route==='workbench'){refreshWorkbench();renderFloats();}else render(); return; }
  if (edit) {
    if (e.key === 'Tab' && e.target.tagName === 'TEXTAREA' && (e.target.dataset.codeKind || 'controlCode' in e.target.dataset)) { e.preventDefault(); const el = e.target; el.setRangeText(el.dataset.codeKind ? '    ' : '  ', el.selectionStart, el.selectionEnd, 'end'); el.dispatchEvent(new Event('input', { bubbles: true })); }
    return;
  }
  if (modal) return;
});
let workspaceNormalizer;
function workspaceNormalization(){return workspaceNormalizer ||= FluidNetWorkspaceNormalization.create({
  parameterDefinitions:PARAM_DEFS,variablesFor,clone,moduleSpecs:MODULE_SPECS,pythonModuleSource,legacyModuleSource,
  defaultGroups:DEFAULT_MODULE_GROUPS,manifestFields,manifestParamSpecs,emptyRun,
  pinProject:(p,allowLegacy)=>engine.pinProject(p,allowLegacy),normalizeControls:p=>controls.normalize(p),
  moduleOf,validateInstanceVariableState,ensureInstanceVariables,rehome:p=>links.rehome(p),projectVariables
});}
function backfillBuiltinParams(data){return workspaceNormalization().backfillBuiltinParams(data);}
function normalizeState(){
  workspaceNormalization().normalize(state);
  if(ui.category!=='全部模块'&&!moduleGroupNames().includes(ui.category))ui.category='全部模块';
}
const chartRegistry = new Map();
engine = createEngineClient({state:()=>state, project, parameterKey:projectParameterKey, moduleOf,
  prepareLegacyParameters:()=>backfillBuiltinParams(state),
  makeProject,
  persist:()=>persistLocal(),
  restoreWorkspace,validateWorkspace:validateImport,archives:receiveArchives,showArchive,showResumedProject:owner=>openProject(owner.id),
  moduleOutput:(m,text)=>{m.authoringOutput=text;if(m.id===state.selectedModule){const el=document.getElementById('module-output') || document.getElementById('code-output');if(el){el.textContent=text;document.getElementById('authoring-diagnostics')?.remove();el.insertAdjacentHTML('afterend',renderAuthoringDiagnostics(m));}}},
  parameterDefinitions:PARAM_DEFS, emptyRun, render:()=>retainFocus(), refresh:refreshLive,
  refreshRun:()=>{if(ui.route==='workbench'){refreshWorkbench();refreshLive(false);}else retainFocus();},
  message:msg, diagnostics:showDiagnostics, dirty:markDirty,
  askToken:(reason,done)=>openDialog('输入访问令牌',reason+'令牌由服务端管理员用 python -m fn_engine token create 生成，只保存在当前浏览器标签页。',
    `<label class="field"><span>访问令牌</span><input name="token" type="password" autocomplete="off" required aria-label="访问令牌" placeholder="fn_…"></label>`,
    data=>{if(!data.token?.trim())throw Error('请输入令牌。');done(data.token);},'连接')});
systemInspection=createSystemInspection({engine:()=>engine,project,openDialog,esc,btn,download:downloadFile,
  locate:(projectId,id)=>{const owner=state.projects.find(p=>p.id===projectId),found=owner&&links.locate(owner,id);if(!found){msg('原设备已不在当前项目；请按冻结档案查看。',true);return;}closeDialog();openProject(owner.id);owner.activePage=found.page.id;ui.selectedNode=id;render();openDevice(id);}});
moduleReplay=createModuleReplayUI({request:(...args)=>engine.request(...args),render,navigate,download:downloadFile,message:msg,route:()=>ui.route});
scenarioBatches=createScenarioBatchesUI({engine:()=>engine,ui:()=>ui,project,projectKey:projectParameterKey,
  esc,btn,heading,msg,render,confirm:confirmChange,download:downloadFile});
workflows=createModelingWorkflows({state:()=>state,engine:()=>engine,ui:()=>ui,project,
  esc,btn,openDialog,closeDialog,msg,clone,uid,emptyRun,confirm:confirmChange,paramSpecs:deviceParamSpecs,
  projectKey:projectParameterKey,dirty:markDirty,render,persist:()=>persistLocal(),backup:backupLocalDraft,download:downloadFile,
  replaceState:(next,beforeReplace)=>{replaceWorkspaceState(next,beforeReplace);ui.floats=[];ui.selectedNode='';undoStack=[];redoStack=[];}});
coldStorage=createColdStorageUI({state:()=>state,engine:()=>engine,ui:()=>ui,makeInstance,makeProject,project,
  replaceState:replaceWorkspaceState,emptyRun,
  uid,normalizeState,markDirty,persist:()=>persistLocal(),openProject,msg,esc,btn,openDialog,closeDialog,render,fitNetwork,remember,moduleOf,
  download:downloadFile,projectKey:projectParameterKey});
airSide=createAirSideUI({state:()=>state,engine:()=>engine,ui:()=>ui,project,moduleOf,projectKey:projectParameterKey,
  esc,btn,heading,msg,render,markDirty,persist:()=>persistLocal(),openDialog,closeDialog,makeInstance,makeProject,uid,
  normalizeState,openProject,navigate,download:downloadFile});
try { normalizeState(); } catch { state = initialState(); normalizeState(); recovery = '原型记录不完整，已恢复内置示例。'; }
function routeFromLocation() {
  const route = location.hash.slice(1);
  if (PAGE_META[route]) return route;
  if (route) history.replaceState(null, '', '#home');
  return 'home';
}
ui.route = routeFromLocation();
workspaceInteractions().mount();
render();
engine.init();
window.addEventListener('hashchange', () => { moduleReplay?.navigationChanged(); ui.route = routeFromLocation(); render(); });
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { renderFloats(); if (['curves', 'workbench'].includes(ui.route)) refreshLive(); }, 120); });
runInterval = setInterval(() => engine.tick(), 200);

}
