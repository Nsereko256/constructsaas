import{c as i,N as d,O as t,Q as s,u as p,j as n,W as u,I as f,R as c}from"./index-Ds-TTcsB.js";/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=i("Route",[["circle",{cx:"6",cy:"19",r:"3",key:"1kj8tv"}],["path",{d:"M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15",key:"1d8sl"}],["circle",{cx:"18",cy:"5",r:"3",key:"gq8acd"}]]);/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=i("Warehouse",[["path",{d:"M22 8.35V20a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8.35A2 2 0 0 1 3.26 6.5l8-3.2a2 2 0 0 1 1.48 0l8 3.2A2 2 0 0 1 22 8.35Z",key:"gksnxg"}],["path",{d:"M6 18h12",key:"9pbo8z"}],["path",{d:"M6 14h12",key:"4cwo0f"}],["rect",{width:"12",height:"12",x:"6",y:"10",key:"apd30q"}]]),y={list:e=>s(`/api/external-move-orders/${t(e)}`),detail:e=>s(`/api/external-move-orders/${e}/`),create:e=>s("/api/external-move-orders/",{method:"POST",body:e}),action:(e,a,r)=>s(`/api/external-move-orders/${e}/${a}/`,{method:"POST",body:r}),download:(e,a,r={})=>{const o=typeof window<"u"?window.localStorage.getItem("construct.active-project-site"):null,l=a?{}:{...r,...o?{project_site:o}:{}};return d(`/api/external-move-orders/${a?`${a}/`:""}download/${e}/${t(l)}`,`${a?`move-order-MO-${a}`:"move-orders"}.${e}`)}},x=e=>["admin","storekeeper","procurement_officer","finance_manager","finance_officer","finance_viewer"].includes(e||"");async function $(e){const a=[];for(let r=1;;r++){const o=await s(`${e}${e.includes("?")?"&":"?"}page=${r}&page_size=100`,{},!0,!1);if(a.push(...o.results),!o.next)return a}}function w(){const{role:e}=p();return n.jsx("div",{className:"ops-tabs",children:n.jsx(u,{links:[{href:"/inventory",label:"Stock",icon:f},{href:"/inventory/warehouses",label:"Warehouses",icon:m},...x(e)?[{href:"/inventory/external-transfers",label:"External transfers",icon:c}]:[],{href:"/inventory/bin-locations",label:"Bin locations",icon:c},{href:"/inventory/movements",label:"Movements",icon:h}]})})}export{w as I,h as R,$ as a,x as c,y as e};
