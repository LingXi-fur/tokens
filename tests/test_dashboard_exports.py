import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "tokens_cli" / "dashboard_assets" / "dashboard.js"
HAVE_NODE = shutil.which("node") is not None
if os.environ.get("CI") and not HAVE_NODE:

    def requires_node(test):
        def wrapper(self):
            self.fail("Node.js is required for dashboard JavaScript contract tests")

        return wrapper

else:
    requires_node = unittest.skipUnless(
        HAVE_NODE,
        "Node.js is required for dashboard JavaScript contract tests",
    )


class DashboardExportTests(unittest.TestCase):
    @requires_node
    def test_csv_and_markdown_exports_execute_with_escaping(self):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("function markdownCell")
        end = source.index("function openHelp", start)
        export_source = source[start:end]

        node_script = r'''
const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('function markdownCell');
const end=source.indexOf('function openHelp',start);
const exportSource=source.slice(start,end);
const downloads=[];
const listeners={};
const context={
  DATA:{
    models:['model-a','model-b'],
    pretty:{'model-a':'Model, "A"','model-b':'Model|B'},
    generated:'2026-07-03T00:00:00Z',
  },
  state:{gran:'day',models:new Set(['model-a','model-b'])},
  LABEL:{day:'日期'},
  dashboardLanguage:'zh',
  selectedRows:()=>[
    {period:'2026-07-01',total:12,'models':undefined,calls:2},
  ],
  pretty:model=>context.DATA.pretty[model]||model,
  fmt:value=>String(value),
  toast:()=>{},
  URL:{
    createObjectURL(blob){downloads.push({blob});return 'blob:test';},
    revokeObjectURL(){},
  },
  Blob,
  setTimeout:fn=>fn(),
  document:{
    createElement(){return {click(){const item=downloads.at(-1);item.filename=this.download;item.type=item.blob.type;}};},
    getElementById(id){return {addEventListener(type,fn){listeners[id+':'+type]=fn;}};},
  },
};
context.selectedRows=()=>[
  {period:'2026-07-01',total:12,models:{'model-a':7,'model-b':5},calls:2},
  {period:'line\nbreak',total:4,models:{'model-a':4,'model-b':0},calls:1},
];
vm.createContext(context);
vm.runInContext(exportSource,context);
if(typeof context.exportCSV!=='function'||typeof context.exportMarkdown!=='function')throw new Error('export functions unavailable');
context.exportCSV();
context.exportMarkdown();
context.dashboardLanguage='en';
context.exportMarkdown();
Promise.all(downloads.map(async item=>({...item,text:await item.blob.text()}))).then(items=>{
  const csv=items.find(item=>item.filename==='tokens-day.csv');
  const md=items.find(item=>item.filename==='tokens-day.md');
  const mdZh=items[1];
  const mdEn=items[2];
  if(!csv||!md||!mdZh||!mdEn)throw new Error('expected filenames missing');
  if(!csv.text.startsWith('period,total_tokens,"Model, ""A""",Model|B,calls\n'))throw new Error('CSV header escaping failed: '+JSON.stringify(csv.text));
  if(!csv.text.includes('"line\nbreak",4,4,0,1'))throw new Error('CSV newline escaping failed');
  if(!mdZh.text.includes('| 日期 | 总 token | Model, "A" | Model\\|B | 调用 |'))throw new Error('Chinese Markdown header escaping failed: '+JSON.stringify(mdZh.text));
  if(!mdEn.text.includes('| Date | Total tokens | Model, "A" | Model\\|B | Calls |'))throw new Error('English Markdown header escaping failed: '+JSON.stringify(mdEn.text));
  if(!mdEn.text.includes('> Generated locally on '))throw new Error('English footer missing');
  if(!mdZh.text.includes('| line break | 4 | 4 | 0 | 1 |'))throw new Error('Markdown newline escaping failed');
  if(!listeners['csv-btn:click']||!listeners['md-btn:click'])throw new Error('button bindings missing');
  process.stdout.write(JSON.stringify(items.map(({filename,type,text})=>({filename,type,text}))));
}).catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(
            ["node", "-e", node_script, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("tokens-day.csv", result.stdout)
        self.assertIn("tokens-day.md", result.stdout)
        self.assertIn("document.getElementById('csv-btn').addEventListener('click', exportCSV)", export_source)
        self.assertIn("document.getElementById('md-btn').addEventListener('click',exportMarkdown)", export_source)

    def test_csv_keyboard_shortcut_remains_bound(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("else if(e.key==='e'||e.key==='E') exportCSV();", source)

    @requires_node
    def test_interval_and_scrub_hints_have_no_chinese_residue_in_english(self):
        node_script = r'''
const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const translation=source.slice(source.indexOf('const I18N_EXACT'),source.indexOf('function localizeTextNode'));
const context={document:{documentElement:{lang:'en'}}};
vm.createContext(context);
vm.runInContext(translation+'\nthis.translate=englishText;',context);
const samples=[
 '2026-09-27 · 123 Token · 主力 gpt-6-sol 50% · Enter / Space / 点击选择区间',
 '预览 2026-09-27 · 123 Token。按提示选择 A/B 周期。',
 '正在预览 2026-09-27 · 123 tk · 点柱或按 Enter 选择时段',
 '正在预览 2026-09-27 · 123 tk · 松开仍为预览，点击或按 Enter 提交',
 '预览 2026-09-27 · 123 Token。提交后进入时光探针。',
];
for(const text of samples){
  const translated=context.translate(text);
  if(/[㐀-鿿]/.test(translated))throw new Error('CJK residue after English translation: '+translated);
}
'''
        result = subprocess.run(
            ["node", "-e", node_script, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
