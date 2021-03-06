import numpy as np
import torch
import torch.nn.functional as F
from torchvision.utils import make_grid
from base import BaseTrainer, BaseTrainerEnsemble
from utils import inf_loop, MetricTracker
from torch.autograd import grad

class TrainerDeEnsemble(BaseTrainerEnsemble):
    """
    Trainer class
    """
    def __init__(self, models, criterion, metric_ftns, optimizers, config, data_loader,
                 valid_data_loader=None, lr_schedulers=None, len_epoch=None):
        super().__init__(models, criterion, metric_ftns, optimizers, config)
        self.config = config
        self.data_loader = data_loader
        if len_epoch is None:
            # epoch-based training
            self.len_epoch = len(self.data_loader)
        else:
            # iteration-based training
            self.data_loader = inf_loop(data_loader)
            self.len_epoch = len_epoch
        self.valid_data_loader = valid_data_loader
        self.do_validation = self.valid_data_loader is not None
        self.lr_schedulers = lr_schedulers
        self.log_step = int(np.sqrt(data_loader.batch_size))
        self.n_batches = data_loader.n_samples / data_loader.batch_size

        self.train_metrics = MetricTracker(*['loss_' + str(i)  for i in range(self.n_ensembles)], *[m.__name__ + '_' + str(i) for m in self.metric_ftns for i in range(self.n_ensembles)], writer=self.writer)
        self.valid_metrics = MetricTracker(*['loss_' + str(i)  for i in range(self.n_ensembles)], *[m.__name__ + '_' + str(i) for m in self.metric_ftns for i in range(self.n_ensembles)], writer=self.writer)

        if self.do_validation:
            keys_val = ['val_' + k for k in self.keys]
            for key in self.keys + keys_val:
                self.log[key] = []

        cfg_loss = config['trainer']['loss']
        self.alpha = cfg_loss['alpha']
        self.epsilon = cfg_loss['epsilon']

    def _train_epoch(self, epoch):
        """
        Training logic for an epoch

        :param epoch: Integer, current training epoch.
        :return: A log that contains average loss and metric in this epoch.
        """
        self.train_metrics.reset()
        for i, (model, optimizer, lr_scheduler) in enumerate(zip(self.models, self.optimizers, self.lr_schedulers)):
            model.train()
            for batch_idx, (data, target) in enumerate(self.data_loader):
                data, target = data.to(self.device), target.to(self.device)
                data.requires_grad = True
                optimizer.zero_grad()

                output = model(data)
                nll_loss = self.criterion(output, target)

                nll_grad = grad(self.alpha * nll_loss, data, retain_graph=True, create_graph=True)[0]
                x_at = data + self.epsilon * torch.sign(nll_grad)

                out_at = model(x_at)

                nll_loss_at = self.criterion(out_at, target)

                loss = self.alpha * nll_loss + (1 - self.alpha) * nll_loss_at

                loss.backward()
                optimizer.step()

                self.writer.set_step((epoch - 1) * self.len_epoch + batch_idx)
                self.train_metrics.update('loss_' + str(i), loss.item())
                for met in self.metric_ftns:
                    self.train_metrics.update(met.__name__ + '_' + str(i), met(output, target, type="DE"))

                if batch_idx % self.log_step == 0:
                    self.logger.debug('Train Epoch: {} {} {} Loss: {:.6f}'.format(
                        'Net_' + str(i),
                        epoch,
                        self._progress(batch_idx),
                        loss.item()))
                    # self.writer.add_image('input', make_grid(data.cpu(), nrow=8, normalize=True))

                if batch_idx == self.len_epoch:
                    break

            if lr_scheduler is not None:
                lr_scheduler.step()

        log = self.train_metrics.result()

        if self.do_validation:
            val_log = self._valid_epoch(epoch)
            log.update(**{'val_'+k : v for k, v in val_log.items()})

        return log

    def _valid_epoch(self, epoch):
        """
        Validate after training an epoch

        :param epoch: Integer, current training epoch.
        :return: A log that contains information about validation
        """
        self.valid_metrics.reset()
        for i, (model, optimizer, lr_scheduler) in enumerate(zip(self.models, self.optimizers, self.lr_schedulers)):
            model.eval()
            with torch.no_grad():
                for batch_idx, (data, target) in enumerate(self.valid_data_loader):
                    data, target = data.to(self.device), target.to(self.device)

                    output = model(data)
                    loss = self.criterion(output, target)

                    self.writer.set_step((epoch - 1) * len(self.valid_data_loader) + batch_idx, 'valid')
                    self.valid_metrics.update('loss_' + str(i), loss.item())
                    for met in self.metric_ftns:
                        self.valid_metrics.update(met.__name__ + '_' + str(i), met(output, target, type="DE"))
                    # self.writer.add_image('input', make_grid(data.cpu(), nrow=8, normalize=True))

            # add histogram of model parameters to the tensorboard
            for name, p in model.named_parameters():
                self.writer.add_histogram(name, p, bins='auto')

        return self.valid_metrics.result()

    def _progress(self, batch_idx):
        base = '[{}/{} ({:.0f}%)]'
        if hasattr(self.data_loader, 'n_samples'):
            current = batch_idx * self.data_loader.batch_size
            total = self.data_loader.n_samples
        else:
            current = batch_idx
            total = self.len_epoch
        return base.format(current, total, 100.0 * current / total)
