"""One complete BERT forward on one sequence for each query embedding."""
import torch


class ForwardBudget:
    def __init__(self, model):
        self.active = False
        self.violation = False
        self.counts = {}
        self.hooks = []
        modules = [('backbone', model), ('embeddings', model.embeddings)]
        modules += [('layer-' + str(i), layer) for i, layer in enumerate(model.encoder.layer)]
        for name, module in modules:
            def hook(current, args, kwargs, name=name):
                if not self.active:
                    return
                self.counts[name] += 1
                if self.counts[name] > 1:
                    self.fail('Only one complete E5 forward is allowed per query')
                if name == 'backbone':
                    ids = kwargs.get('input_ids', args[0] if args else None)
                    if (not isinstance(ids, torch.Tensor) or ids.ndim != 2 or
                            ids.shape[0] != 1 or not 1 <= ids.shape[1] <= 512 or
                            kwargs.get('inputs_embeds') is not None):
                        self.fail('Query forward requires one input_ids sequence of at most 512 tokens')
                    mask = kwargs.get('attention_mask', args[1] if len(args) > 1 else None)
                    if mask is not None and (mask.shape != ids.shape or
                            not torch.all((mask == 0) | (mask == 1))):
                        self.fail('Query attention_mask must be a two-dimensional binary padding mask')
            handle = module.register_forward_pre_hook(hook, with_kwargs=True)
            self.hooks.append((name, module, handle, hook))

    def fail(self, message):
        self.violation = True
        raise ValueError(message)

    def begin(self):
        if self.violation:
            self.fail('Previous query forward-budget violation')
        self.counts = {name: 0 for name, _, _, _ in self.hooks}
        self.active = True

    def finish(self):
        self.active = False
        if any(module._forward_pre_hooks.get(handle.id) is not hook
               for _, module, handle, hook in self.hooks):
            self.fail('Query forward-budget instrumentation was changed')
        if any(count != 1 for count in self.counts.values()):
            self.fail('Every query must execute the complete E5 backbone exactly once')
