"""Fixed historical windows; padding is not used to disguise insufficient history."""
import numpy as np

class SequenceModel:
    def __init__(self, steps=6, epochs=15):
        self.steps, self.epochs = steps, epochs
    def fit(self, X, y):
        import torch
        from torch import nn
        torch.manual_seed(42)
        torch.set_num_threads(1)
        class Network(nn.Module):
            def __init__(self, features):
                super().__init__()
                self.conv = nn.Conv1d(features, 16, 3, padding=1)
                self.lstm = nn.LSTM(16, 16, batch_first=True, bidirectional=True)
                self.attention = nn.Linear(32, 1)
                self.head = nn.Linear(32 + features, 1)
            def forward(self, x):
                local = torch.relu(self.conv(x.transpose(1,2))).transpose(1,2)
                hidden, _ = self.lstm(local)
                weights = torch.softmax(self.attention(hidden), dim=1)
                fused = torch.cat([(hidden * weights).sum(dim=1), x[:,-1]], dim=1)
                return self.head(fused).squeeze(-1), weights.squeeze(-1)
        # Keep a serializable state dictionary, not this local network class.
        self.features = X.shape[-1]
        self._factory = None
        net = Network(self.features)
        tx = torch.tensor(X, dtype=torch.float32)
        ty = torch.tensor(np.asarray(y), dtype=torch.float32)
        loss = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(float((ty==0).sum()/max(1, int((ty==1).sum())))))
        opt = torch.optim.Adam(net.parameters(), lr=.003)
        for _ in range(self.epochs):
            for indices in torch.randperm(len(tx)).split(64):
                opt.zero_grad()
                loss(net(tx[indices])[0], ty[indices]).backward()
                opt.step()
        self.state = {k:v.detach().numpy() for k,v in net.state_dict().items()}
        return self
    def _forward(self, X):
        import torch
        from torch import nn
        # Reconstitute named layers matching training for safe joblib roundtrips.
        conv = nn.Conv1d(self.features,16,3,padding=1)
        lstm = nn.LSTM(16,16,batch_first=True,bidirectional=True)
        attention, head = nn.Linear(32,1), nn.Linear(32+self.features,1)
        for name, layer in [('conv',conv),('lstm',lstm),('attention',attention),('head',head)]:
            layer.load_state_dict({k[len(name)+1:]:torch.tensor(v) for k,v in self.state.items() if k.startswith(name+'.')})
            layer.eval()
        with torch.no_grad():
            x = torch.tensor(X, dtype=torch.float32)
            h,_ = lstm(torch.relu(conv(x.transpose(1,2))).transpose(1,2))
            w = torch.softmax(attention(h),dim=1)
            p = torch.sigmoid(head(torch.cat([(h*w).sum(1),x[:,-1]],dim=1))).squeeze(-1)
        return p.numpy(), w.squeeze(-1).numpy()
    def predict_proba(self, X):
        p,_ = self._forward(X)
        return np.column_stack([1-p,p])
    def attention_weights(self, X):
        return self._forward(X)[1]

class SequenceAdapter:
    """Pass tabular candidates the last approved historical observation."""
    def __init__(self, model): self.model = model
    def predict_proba(self, X): return self.model.predict_proba(X[:,-1,:])
