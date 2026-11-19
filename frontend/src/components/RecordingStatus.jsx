export function RecordingStatus() {
  return (
    <section aria-labelledby="recording-heading">
      <h2 id="recording-heading">Recording status</h2>
      <p data-testid="recording-state">Inactive</p>
      <p>Live monitoring is active independently; scan observations are not being saved.</p>
    </section>
  );
}