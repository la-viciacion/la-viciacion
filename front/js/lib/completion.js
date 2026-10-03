// Why a library entry cannot be completed, re-dated or unmarked (the API decides, this only words it).

/** `entry.complete_blocked` -> message for the player, or '' when it can be completed. */
export function blockedReason(entry, currentSeason) {
  switch (entry.complete_blocked) {
    case 'closed_season':
      if (entry.completed) return `Temporada ${entry.season} cerrada: su completado ya no se puede cambiar.`;
      return `Temporada ${entry.season} cerrada: solo se pueden completar juegos de la temporada actual (${currentSeason}).`;
    case 'completed_in_season':
      return 'Ya lo has completado esta temporada en otra plataforma.';
    default:
      return '';
  }
}
