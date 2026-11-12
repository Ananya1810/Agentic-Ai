from modules.analytics import cluster_data, make_roadmap

class FeedbackAgent:
    """Simple tool-using agent: plans tools from the user's request and runs them."""
    def __init__(self, data):
        self.data = data
        self.clustered = None
        self.summary = None
        self.roadmap = None

    def run(self, question):
        q = question.lower()
        tools, results, answer = [], {}, []
        wants_summary = any(w in q for w in ["summary","overview","overall","dataset","rating"])
        wants_cluster = any(w in q for w in ["cluster","group","theme","category","feedback","complaint"])
        wants_roadmap = any(w in q for w in ["roadmap","priority","priorit","recommend","improve","problem","action"])
        if not (wants_summary or wants_cluster or wants_roadmap):
            wants_summary = wants_cluster = wants_roadmap = True

        if wants_summary:
            tools.append("dataset_summary")
            avg = self.data["Rating"].mean()
            answer.append(f"Your dataset has **{len(self.data)} reviews**, **{self.data['ProductName'].nunique()} products**, and an average rating of **{avg:.2f}/5**.")

        if wants_cluster or wants_roadmap:
            if self.clustered is None:
                tools.append("TF-IDF + K-Means clustering")
                self.clustered, self.summary = cluster_data(self.data, 5)
            results["clustered"] = self.clustered
            results["clusters"] = self.summary

        if wants_cluster:
            lines = [f"- **{r.ClusterLabel}**: {r.ReviewCount} reviews; average rating {r.AverageRating}/5" for r in self.summary.itertuples()]
            answer.append("I grouped similar reviews into these themes:\n" + "\n".join(lines))

        if wants_roadmap:
            if self.roadmap is None:
                tools.append("roadmap prioritisation")
                self.roadmap = make_roadmap(self.clustered, self.summary)
            results["roadmap"] = self.roadmap
            if not self.roadmap.empty:
                first = self.roadmap.iloc[0]
                answer.append(f"Top theme to investigate: **{first['Theme']}** ({first['Priority']} priority). Suggested action: {first['RecommendedAction']}")
                answer.append("Priority is a prototype score based on theme frequency, low ratings and average rating. Treat it as decision support, not an automatic product decision.")

        results["tools"] = tools
        return "\n\n".join(answer), results
