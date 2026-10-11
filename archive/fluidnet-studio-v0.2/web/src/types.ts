export type Parameters = Record<string, number | string | boolean | number[][]>;
export type ElementModel = { id: string; type: string; name: string; parameters: Parameters;
  media: Record<string, string>; position: { x: number; y: number }; page: number;
  group_id: string | null; version: number; template_id?:string|null; template_revision?:number|null };
export type Connection = { id: string; source: string; source_port: string; target: string; target_port: string };
export type Medium = { id: string; name: string; kind: string; components: string[]; mass_fractions: number[];
  backend: string; backend_fluid: string; phase_policy: string; version: number };
export type ModuleInterface = { exposed_ports:Record<string,string>; exposed_parameters:Record<string,string>; port_labels:Record<string,string>; parameter_labels:Record<string,string> };
export type Group = ModuleInterface & { id: string; name: string; element_ids: string[]; position:{x:number;y:number};page:number;collapsed:boolean;template_id:string|null;template_revision:number|null;member_keys:Record<string,string> };
export type Scenario = { id: string; name: string; overrides: Record<string, Parameters> };
export type Project = { schema_version: 2; id: string; name: string; description: string; revision: number;
  atmosphere_pa: number; initial_temperature_k: number; default_medium_id: string; media: Medium[];
  elements: ElementModel[]; connections: Connection[]; groups: Group[]; scenarios: Scenario[];
  selected_variables: string[]; options: { max_iterations: number; max_thermal_iterations: number;
    mass_atol: number; mass_rtol: number; pressure_atol: number; pressure_rtol: number;
    thermal_tolerance_k: number; thermal: boolean } };
export type ParameterDef = { key: string; label: string; default: Parameters[string]; unit?: string;
  kind: 'number'|'text'|'curve'|'boolean'|'select'; min?: number|null; max?: number|null;
  positive?: boolean; runtime?: boolean; choices?: string[] };
export type PortDef = { id: string; label: string; group: string; side: 'left'|'right'|'top'|'bottom'; required: boolean };
export type ComponentDef = { type: string; name: string; category: string; icon: string; description: string;
  ports: PortDef[]; parameters: ParameterDef[]; version: number; supported_media: string[]; control?: boolean; boundary?: boolean };
export type Catalog = { components: ComponentDef[]; variables: Record<string,{label:string;unit:string}>;
  media: {kind:string;name:string;enabled:boolean;description:string;backend:string|null;model:string|null}[] };
export type Diagnostic = { code: string; message: string; severity: string; element_id?: string|null; field?: string|null };
export type Circuit = { id: string; medium_id: string; ports: string[] };
export type Snapshot = { valid: boolean; status: string; time_s: number; project_id?: string; project_revision?: number;
  elements: Record<string,Record<string,number>>; ports: Record<string,{pressure_pa:number;temperature_k:number;medium_id:string}>;
  circuits?: Circuit[]; diagnostics: Diagnostic[]; metrics: Record<string,number|null>;
  convergence_history?: {iteration:number;scaled_residual:number}[]; last_valid_state?: boolean; simulation_status?: string };
export type Run = { id:string; name:string; status:string; mode:string; started:number; updated:number;
  project_id:string; frame:Snapshot|null; sequence?:number; request?:{project:Project;scenario_id?:string;dt_s:number;duration_s:number}; command_error?:Diagnostic|null };
export type History = {variables:string[];rows:(number|null)[][];total_rows:number};
export type TemplateDraft = {name:string;kind:'equipment'|'group';body:ElementModel|Project;interface:ModuleInterface;test_conditions:Record<string,{pressure_pa:number;temperature_k:number}>;revision:number;id?:string};
export type Template = TemplateDraft & {id:string;updated:number;archived:boolean;validation_error?:string};
export type ModuleResult = {project:Project;group_id:string|null;element_ids:string[]};
export type TemplatePreview = {project:Project;changes:{added:string[];removed:string[];parameters:string[];interfaces:string[];connections:number}};
export type ProjectInfo = {id:string;name:string;revision:number;updated:number};
export type Units = {flow:'mass'|'volume';pressure:'gauge'|'absolute';temperature:'celsius'|'kelvin'};

export const uid = () => crypto.randomUUID().replaceAll('-', '').slice(0, 16);
export const copy = <T,>(value:T):T => structuredClone(value);
export const DEFAULT_WATER:Medium = {id:'water',name:'液态水',kind:'water',components:['Water'],mass_fractions:[1],backend:'coolprop_if97',backend_fluid:'IF97::Water',phase_policy:'liquid',version:1};
export function blankProject():Project {
  return {schema_version:2,id:uid(),name:'新建流体网络',description:'',revision:0,atmosphere_pa:101325,
    initial_temperature_k:293.15,default_medium_id:'water',media:[copy(DEFAULT_WATER)],elements:[],connections:[],
    groups:[],scenarios:[],selected_variables:[],options:{max_iterations:100,max_thermal_iterations:80,
      mass_atol:1e-8,mass_rtol:1e-6,pressure_atol:1,pressure_rtol:1e-6,thermal_tolerance_k:1e-5,thermal:true}};
}
