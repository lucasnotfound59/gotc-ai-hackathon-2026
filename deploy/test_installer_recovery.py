import hashlib, importlib.util, io, sys, tarfile, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

def load(path):
    spec=importlib.util.spec_from_file_location('installer_recovery',path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

class InstallerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.mod=load(Path(__file__).parent/'install.py')
    def tearDown(self): self.tmp.cleanup()
    def setup_tree(self):
        root=(self.root/'root').resolve(); root.mkdir(); (root/'.gotc-owned').write_text('owned'); (root/'incoming').mkdir(); (root/'releases').mkdir(); (root/'backups').mkdir()
        old=root/'releases'/'old'; old.mkdir(); (root/'current').symlink_to(old,target_is_directory=True)
        nginx=self.root/'nginx'; nginx.write_text('server { listen 443; server_name 8.141.114.201; }\n'); unit=self.root/'unit'; unit.write_text('old unit\n')
        src=self.root/'src'; (src/'server').mkdir(parents=True); (src/'server/app.py').write_text('x=1\n')
        for n in self.mod.FILES:
            p=src/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('x\n')
        arc=root/'incoming'/'r.tar.gz'
        with tarfile.open(arc,'w:gz') as t:
            for p in src.rglob('*'):
                if p.is_file(): t.add(p,p.relative_to(src).as_posix())
        return root,nginx,unit,arc
    def run_it(self, fail=False):
        root,nginx,unit,arc=self.setup_tree(); digest=hashlib.sha256(arc.read_bytes()).hexdigest(); calls=[]
        class R: returncode=0
        def run(*a,**k): calls.append(a); return R()
        count=[0]
        def health(url):
            count[0]+=1
            if fail and count[0] <= 25: raise RuntimeError('synthetic health failure')
            return {'teams':0,'serverTime':1}
        argv=['install.py','--archive',str(arc),'--sha256',digest,'--release','20261030T000000Z-abcdef123456','--source-sha','a'*40]
        with patch.object(self.mod,'ROOT',root),patch.object(self.mod,'NGINX',nginx),patch.object(self.mod,'UNIT',unit),patch.object(self.mod,'run',side_effect=run),patch.object(self.mod,'health',side_effect=health),patch.object(self.mod.os,'geteuid',return_value=0),patch.object(self.mod.time,'sleep'),patch.object(sys,'argv',argv):
            if fail:
                with self.assertRaises(RuntimeError): self.mod.main()
            else: self.mod.main()
        return root,nginx,unit,calls
    def test_normal_isolated_tree(self):
        root,nginx,unit,calls=self.run_it(); self.assertEqual((root/'current').resolve(),root/'releases'/'20261030T000000Z-abcdef123456'); self.assertIn('/gotc/',nginx.read_text()); self.assertIn('ExecStart=',unit.read_text())
    def test_concurrent_nginx_change_is_not_overwritten(self):
        root,nginx,unit,arc=self.setup_tree(); digest=hashlib.sha256(arc.read_bytes()).hexdigest()
        class R: returncode=0
        def run(*a,**k): return R()
        def health(url):
            nginx.write_text('concurrent admin change\\n'); raise RuntimeError('synthetic health failure')
        argv=['install.py','--archive',str(arc),'--sha256',digest,'--release','20261030T000000Z-abcdef123456','--source-sha','a'*40]
        with patch.object(self.mod,'ROOT',root),patch.object(self.mod,'NGINX',nginx),patch.object(self.mod,'UNIT',unit),patch.object(self.mod,'run',side_effect=run),patch.object(self.mod,'health',side_effect=health),patch.object(self.mod.os,'geteuid',return_value=0),patch.object(self.mod.time,'sleep'),patch.object(sys,'argv',argv):
            with self.assertRaises(RuntimeError): self.mod.main()
        self.assertEqual(nginx.read_text(),'concurrent admin change\\n')

    def test_external_health_failure_restores_state(self):
        root,nginx,unit,arc=self.setup_tree(); digest=hashlib.sha256(arc.read_bytes()).hexdigest(); count=[0]
        class R: returncode=0
        def run(*a,**k): return R()
        def health(url):
            count[0]+=1
            if count[0] > 1: raise RuntimeError('synthetic external health failure')
            return {'teams':0,'serverTime':1}
        argv=['install.py','--archive',str(arc),'--sha256',digest,'--release','20261030T000000Z-abcdef123456','--source-sha','a'*40]
        with patch.object(self.mod,'ROOT',root),patch.object(self.mod,'NGINX',nginx),patch.object(self.mod,'UNIT',unit),patch.object(self.mod,'run',side_effect=run),patch.object(self.mod,'health',side_effect=health),patch.object(self.mod.os,'geteuid',return_value=0),patch.object(self.mod.time,'sleep'),patch.object(sys,'argv',argv):
            with self.assertRaises(RuntimeError): self.mod.main()
        self.assertEqual(nginx.read_text(),'server { listen 443; server_name 8.141.114.201; }\n'); self.assertEqual((root/'current').resolve(),root/'releases'/'old')

    def test_health_failure_restores_state(self):
        root,nginx,unit,calls=self.run_it(True); self.assertEqual((root/'current').resolve(),root/'releases'/'old'); self.assertEqual(nginx.read_text(),'server { listen 443; server_name 8.141.114.201; }\n'); self.assertEqual(unit.read_text(),'old unit\n')

if __name__=='__main__': unittest.main()
