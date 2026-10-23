"""Optional reproducible simple baselines. All work uses public inputs only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from gold import feasible,top_ids
from metrics import PROPERTIES,TARGETS
from gpu_tables import TensorTables

ROOT=Path(__file__).resolve().parent
SUBMISSION=Path('/app/submission')


def configuration():
    config=SUBMISSION/'baseline-config.json'
    if not config.exists():config=ROOT/'baseline-default.json'
    return json.loads(config.read_text())


def family():
    return configuration()['family']


def run(script,*arguments):
    env={**os.environ,'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    subprocess.run([sys.executable,str(ROOT/script),*map(str,arguments)],check=True,env=env)


def materialize_apex(library_dir,model_dir,index,mode):
    import torch
    from library import Library
    torch.set_num_threads(1)
    library=Library(library_dir)
    if len(library)!=12446577:raise ValueError('The supplied APEX cache is for the 12M library')
    state=torch.load(Path(model_dir)/'apex_brics_csl_12M.pt',map_location='cpu',weights_only=True)['model_state_dict']
    names=torch.load(Path(model_dir)/'probe.pt',map_location='cpu',weights_only=True)['output_names']
    columns=[names.index('score_'+t) for t in TARGETS]
    props=[names.index(name) for name in PROPERTIES]
    values=state['library_tensors.synthon_associative_contribs'].numpy()
    scale=state['probe.output_scale'].numpy();bias=state['probe.bias'].numpy()
    mapping={tuple(key):i for i,key in enumerate(state['library_indexes.synthon2rgroup'].T.tolist())}
    shifts=state['library_indexes.first_rgroup_by_reaction'].tolist()
    scores=np.lib.format.open_memmap(index/'scores.npy',mode='w+',dtype=np.float32,shape=(len(library),5))
    properties=(np.lib.format.open_memmap(index/'properties.npy',mode='w+',dtype=np.float32,
                 shape=(len(library),6)) if mode=='apex-pred' else None)
    for r,groups in enumerate(library.tree):
        shape=library.shapes[r];prediction=np.zeros(shape+(len(names),),dtype=np.float32)
        for position,group in enumerate(groups):
            ids=[mapping[(s,shifts[r]+position)] for s in group]
            axes=[1]*len(groups);axes[position]=len(group)
            prediction+=values[ids].reshape(tuple(axes)+(len(names),))
        prediction=prediction.reshape(-1,len(names))*scale+bias
        left,right=library.offsets[r:r+2];scores[left:right]=prediction[:,columns]
        if properties is not None:properties[left:right]=prediction[:,props]
    scores.flush()
    if properties is not None:properties.flush()


def prepare(library_dir,model_dir,index_dir):
    mode=family();index=Path(index_dir);index.mkdir(exist_ok=True)
    cached=SUBMISSION/'baseline-index'
    if mode=='native' or all((cached/name).is_file() for name in ['scores.npy','properties.npy']):return
    if mode=='simple-ensemble':
        config=configuration();fragments=index/'fragments.json'
        run('baseline_fragments.py','--library-dir',library_dir,'--output',fragments)
        for view in ['raw','normalized']:
            directory=index/view;directory.mkdir(exist_ok=True)
            arguments=['--library-dir',library_dir,'--models-dir',model_dir,'--output-dir',directory,
                       '--workers','14','--batch-size','1024','--threads','2']
            if view=='normalized':arguments+=['--normalized-fragments',fragments]
            run('baseline_model.py',*arguments)
            arguments=['--library-dir',library_dir,'--output-dir',directory]
            if view=='normalized':arguments+=['--normalized-fragments',fragments]
            run('baseline_properties.py',*arguments)
        score_views={view:np.load(index/view/'full-surrogate-scores.npy',mmap_mode='r') for view in ['raw','normalized']}
        prop_views={view:np.load(index/view/'properties.npy',mmap_mode='r') for view in ['raw','normalized']}
        scores=np.lib.format.open_memmap(index/'scores.npy',mode='w+',dtype=np.float32,shape=score_views['raw'].shape)
        for t,target in enumerate(TARGETS):
            choice=config['score_choices'][target];a=choice['fraction']
            scores[:,t]=a*score_views[choice['family']][:,t]+(1-a)*score_views['normalized'][:,t]
        scores.flush()
        props=np.lib.format.open_memmap(index/'properties.npy',mode='w+',dtype=np.float32,shape=prop_views['raw'].shape)
        for j,name in enumerate(PROPERTIES):
            view=config['property_sources'][j] if config['property_mode']=='simple-hybrid' else config['property_mode']
            props[:,j]=prop_views[view][:,j]
        props.flush();return
    normalized=mode in ['apex-normalized','full-normalized-properties','full-normalized']
    fragments=index/'fragments.json'
    if normalized:
        run('baseline_fragments.py','--library-dir',library_dir,'--output',fragments)
    if mode.startswith('full-'):
        arguments=['--library-dir',library_dir,'--models-dir',model_dir,'--output-dir',index,
                   '--workers','14','--batch-size','1024','--threads','2']
        if mode=='full-normalized':arguments+=['--normalized-fragments',fragments]
        run('baseline_model.py',*arguments)
        (index/'full-surrogate-scores.npy').rename(index/'scores.npy')
    elif mode.startswith('apex-'):
        materialize_apex(library_dir,model_dir,index,mode)
    else:raise ValueError('Unknown baseline family: '+mode)
    if mode!='apex-pred':
        arguments=['--library-dir',library_dir,'--output-dir',index]
        if normalized:arguments+=['--normalized-fragments',fragments]
        run('baseline_properties.py',*arguments)


class Searcher:
    def __init__(self,library_dir,model_dir,index_dir):
        self.native=None
        if family()=='native':
            from baseline_native import Searcher as Native
            self.native=Native(library_dir,model_dir,index_dir);return
        cached=SUBMISSION/'baseline-index'
        index=cached if all((cached/name).is_file() for name in ['scores.npy','properties.npy']) else Path(index_dir)
        self.properties=np.load(index/'properties.npy');self.scores=np.load(index/'scores.npy')
        n=json.loads((Path(library_dir)/'library.json').read_text())['n_products']
        if self.scores.shape!=(n,5) or self.properties.shape!=(n,6):raise ValueError('Baseline table/library mismatch')
        members=Path(library_dir).parent/'candidate_ids.npy'
        self.membership=None
        if members.exists():
            self.membership=np.zeros(n,dtype=bool)
            self.membership[np.load(members)]=True
        self.tables=TensorTables(self.properties,self.scores,self.membership)
        del self.properties,self.scores

    def search(self,query):
        if self.native is not None:return self.native.search(query)
        return self.tables.search(query)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Build optional public baseline artifacts during development')
    parser.add_argument('--library-dir',default='/task/library')
    parser.add_argument('--models-dir',default='/task/models')
    parser.add_argument('--output',default='/app/submission/baseline-index')
    args=parser.parse_args()
    prepare(args.library_dir,args.models_dir,args.output)
